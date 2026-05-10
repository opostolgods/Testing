/* ═══════════════════════════════════════════════════════
   CloudVPN — Frontend Application
   ═══════════════════════════════════════════════════════ */

let currentUser = null;
let currentPage = 'landing';
let botUsername = 'CloudVPN_bestbot';

// ── Init ────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  await loadConfig();
  await checkAuth();
  renderAuthArea();

  // Handle hash navigation
  const hash = window.location.hash.replace('#', '');
  if (['dashboard', 'tutorials', 'support', 'admin'].includes(hash)) {
    navigateTo(hash);
  }
});

// ── Config ──────────────────────────────────────────────

async function loadConfig() {
  try {
    const resp = await fetch('/api/config');
    const data = await resp.json();
    if (data.bot_username) botUsername = data.bot_username;
  } catch (e) {
    console.warn('Config load failed:', e);
  }
}

// ── Auth ────────────────────────────────────────────────

async function checkAuth() {
  try {
    const resp = await fetch('/api/auth/me', { credentials: 'include' });
    if (resp.ok) {
      const data = await resp.json();
      currentUser = data.user;
    }
  } catch (e) {
    currentUser = null;
  }
}

function renderAuthArea() {
  const area = document.getElementById('auth-area');
  if (!area) return;

  if (currentUser) {
    const isAdmin = currentUser.is_admin;
    area.innerHTML = `
      ${isAdmin ? '<a href="#" class="btn-nav-ghost" onclick="navigateTo(\'admin\')">Admin</a>' : ''}
      <a href="#" class="btn-nav" onclick="navigateTo('dashboard')">Кабинет</a>
    `;
  } else {
    area.innerHTML = `<a href="#" class="btn-nav" onclick="navigateTo('dashboard')">Войти</a>`;
  }
}

function renderTelegramWidget() {
  const container = document.getElementById('telegram-login-widget');
  if (!container) return;
  container.innerHTML = '';

  const script = document.createElement('script');
  script.src = 'https://telegram.org/js/telegram-widget.js?22';
  script.setAttribute('data-telegram-login', botUsername);
  script.setAttribute('data-size', 'large');
  script.setAttribute('data-onauth', 'onTelegramAuth(user)');
  script.setAttribute('data-request-access', 'write');
  script.setAttribute('data-radius', '8');
  script.async = true;
  container.appendChild(script);
}

window.onTelegramAuth = async function(user) {
  try {
    const resp = await fetch('/api/auth/telegram', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(user),
    });

    if (resp.ok) {
      const data = await resp.json();
      currentUser = data.user;
      renderAuthArea();
      showDashboard();
      showToast('Вы успешно вошли!');
    } else {
      const err = await resp.json();
      showToast('Ошибка входа: ' + (err.detail || 'Неизвестная ошибка'));
    }
  } catch (e) {
    showToast('Ошибка соединения');
  }
};

async function logout() {
  try {
    await fetch('/api/auth/logout', {
      method: 'POST',
      credentials: 'include',
    });
  } catch (e) {}
  currentUser = null;
  renderAuthArea();
  navigateTo('landing');
  showToast('Вы вышли из аккаунта');
}

// ── Navigation ──────────────────────────────────────────

function navigateTo(page) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  const el = document.getElementById('page-' + page);
  if (el) {
    el.classList.add('active');
    currentPage = page;
    window.location.hash = page === 'landing' ? '' : page;
    window.scrollTo(0, 0);
  }

  if (page === 'dashboard') {
    if (currentUser) {
      showDashboard();
    } else {
      document.getElementById('login-prompt').style.display = 'flex';
      document.getElementById('dashboard-content').style.display = 'none';
      renderTelegramWidget();
    }
  }

  if (page === 'admin' && currentUser) {
    loadAdminData();
  }
}

// ── Dashboard ───────────────────────────────────────────

function showDashboard() {
  document.getElementById('login-prompt').style.display = 'none';
  document.getElementById('dashboard-content').style.display = 'block';

  const avatar = document.getElementById('dash-avatar');
  if (currentUser.photo_url) {
    avatar.src = currentUser.photo_url;
  } else {
    avatar.src = 'data:image/svg+xml,' + encodeURIComponent(
      '<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48"><rect fill="#1b1c1e" width="48" height="48" rx="24"/><text x="24" y="30" text-anchor="middle" fill="#9c9c9d" font-size="20" font-family="Inter,sans-serif">' +
      (currentUser.first_name || 'U').charAt(0).toUpperCase() + '</text></svg>'
    );
  }

  document.getElementById('dash-name').textContent =
    (currentUser.first_name || '') + ' ' + (currentUser.last_name || '');
  document.getElementById('dash-plan').textContent =
    currentUser.is_premium ? 'Premium' : 'Free Plan';
  document.getElementById('stat-plan').textContent =
    currentUser.is_premium ? 'Premium' : 'Free';

  loadKeys();
}

async function loadKeys() {
  try {
    const resp = await fetch('/api/keys', { credentials: 'include' });
    if (!resp.ok) return;
    const data = await resp.json();
    renderKeys(data.keys || []);
    document.getElementById('stat-keys').textContent = data.keys.length;
  } catch (e) {
    console.error('Failed to load keys:', e);
  }
}

function renderKeys(keys) {
  const container = document.getElementById('keys-list');
  if (!keys.length) {
    container.innerHTML = `
      <div class="empty-state">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#6a6b6c" stroke-width="1.5"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 11-7.78 7.78 5.5 5.5 0 017.78-7.78zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>
        <p>У вас пока нет ключей</p>
        <p class="text-muted">Нажмите «Создать ключ» чтобы начать</p>
      </div>`;
    return;
  }

  container.innerHTML = keys.map(key => {
    const links = key.vless_links || [];
    const expiry = key.expiry_ms ? new Date(key.expiry_ms).toLocaleDateString('ru-RU') : '∞';
    const daysLeft = key.expiry_ms ? Math.max(0, Math.floor((key.expiry_ms - Date.now()) / 86400000)) : 999;
    const expiryColor = daysLeft < 3 ? 'var(--color-ember-red)' : 'var(--color-slate-300)';

    return `
      <div class="key-card">
        <div class="key-header">
          <span class="key-name">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 11-7.78 7.78 5.5 5.5 0 017.78-7.78zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>
            ${key.email}
            <span class="badge ${key.is_premium ? 'badge--premium' : 'badge--free'}">${key.is_premium ? 'Premium' : 'Free'}</span>
          </span>
          <span class="key-expiry" style="color:${expiryColor}">до ${expiry} (${daysLeft}д)</span>
        </div>
        <div class="key-links">
          ${links.map((link, i) => `
            <div class="key-link-row">
              <input class="key-link-input" value="${escapeHtml(link)}" readonly onclick="this.select()">
              <button class="btn btn-ghost btn-sm" onclick="copyKey('${escapeHtml(link)}')" title="Копировать">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
              </button>
            </div>
          `).join('')}
        </div>
        <div class="key-actions">
          ${links.length ? `
            <button class="btn btn-ghost btn-sm" onclick="openInApp('${encodeURIComponent(links[0])}')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
              Открыть в V2RayNG
            </button>
          ` : ''}
          <button class="btn btn-danger btn-sm" onclick="deleteKey('${key.uuid}')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
            Удалить
          </button>
        </div>
      </div>`;
  }).join('');
}

async function createKey() {
  const btn = document.getElementById('btn-create-key');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Создание...';

  try {
    const resp = await fetch('/api/keys/create', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
    });

    if (resp.ok) {
      const data = await resp.json();
      showToast('Ключ создан!');
      loadKeys();
    } else {
      const err = await resp.json();
      showToast('Ошибка: ' + (err.detail || 'Не удалось создать ключ'));
    }
  } catch (e) {
    showToast('Ошибка соединения');
  }

  btn.disabled = false;
  btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M8 2a.75.75 0 01.75.75v4.5h4.5a.75.75 0 010 1.5h-4.5v4.5a.75.75 0 01-1.5 0v-4.5h-4.5a.75.75 0 010-1.5h4.5v-4.5A.75.75 0 018 2z"/></svg> Создать ключ`;
}

async function deleteKey(uuid) {
  if (!confirm('Удалить этот ключ? Это действие нельзя отменить.')) return;

  try {
    const resp = await fetch('/api/keys/' + uuid, {
      method: 'DELETE',
      credentials: 'include',
    });

    if (resp.ok) {
      showToast('Ключ удален');
      loadKeys();
    } else {
      showToast('Не удалось удалить ключ');
    }
  } catch (e) {
    showToast('Ошибка соединения');
  }
}

function copyKey(text) {
  navigator.clipboard.writeText(text).then(() => {
    showToast('Ключ скопирован в буфер обмена');
  }).catch(() => {
    // Fallback
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showToast('Ключ скопирован');
  });
}

function openInApp(encodedLink) {
  const link = decodeURIComponent(encodedLink);
  // v2rayng deep link
  window.location.href = 'v2rayng://install-config?url=' + encodeURIComponent(link);
  setTimeout(() => {
    // Fallback: try intent for Android
    window.location.href = 'intent://install-config?url=' + encodeURIComponent(link) +
      '#Intent;scheme=v2rayng;package=com.v2ray.ang;end';
  }, 2000);
}

// ── Admin ───────────────────────────────────────────────

async function loadAdminData() {
  try {
    const [statsResp, usersResp, keysResp] = await Promise.all([
      fetch('/api/admin/stats', { credentials: 'include' }),
      fetch('/api/admin/users', { credentials: 'include' }),
      fetch('/api/admin/keys', { credentials: 'include' }),
    ]);

    if (statsResp.ok) {
      const { stats } = await statsResp.json();
      document.getElementById('admin-stats').innerHTML = `
        <div class="dash-stat-card">
          <span class="dash-stat-label">Всего пользователей</span>
          <span class="dash-stat-value">${stats.total_users}</span>
        </div>
        <div class="dash-stat-card">
          <span class="dash-stat-label">Premium</span>
          <span class="dash-stat-value">${stats.premium_users}</span>
        </div>
        <div class="dash-stat-card">
          <span class="dash-stat-label">Активных ключей</span>
          <span class="dash-stat-value">${stats.active_keys}</span>
        </div>
      `;
    }

    if (usersResp.ok) {
      const { users } = await usersResp.json();
      document.getElementById('admin-users').innerHTML = `
        <table class="admin-table">
          <thead><tr>
            <th>ID</th><th>Username</th><th>Имя</th><th>Тариф</th><th>Дата регистрации</th><th>Действия</th>
          </tr></thead>
          <tbody>
            ${users.map(u => `
              <tr>
                <td>${u.telegram_id}</td>
                <td>@${escapeHtml(u.username || '—')}</td>
                <td>${escapeHtml(u.first_name || '')} ${escapeHtml(u.last_name || '')}</td>
                <td><span class="badge ${u.is_premium ? 'badge--premium' : 'badge--free'}">${u.is_premium ? 'Premium' : 'Free'}</span></td>
                <td>${u.created_at ? new Date(u.created_at * 1000).toLocaleDateString('ru-RU') : '—'}</td>
                <td>
                  <button class="btn btn-sm ${u.is_premium ? 'btn-danger' : 'btn-ghost'}"
                    onclick="togglePremium(${u.telegram_id}, ${!u.is_premium})">
                    ${u.is_premium ? 'Убрать Premium' : 'Дать Premium'}
                  </button>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>`;
    }

    if (keysResp.ok) {
      const { keys } = await keysResp.json();
      document.getElementById('admin-keys').innerHTML = `
        <table class="admin-table">
          <thead><tr>
            <th>Email</th><th>Пользователь</th><th>Тариф</th><th>Истекает</th><th>Статус</th>
          </tr></thead>
          <tbody>
            ${keys.map(k => `
              <tr>
                <td style="font-family:var(--font-mono);font-size:12px">${escapeHtml(k.email)}</td>
                <td>@${escapeHtml(k.username || '—')}</td>
                <td><span class="badge ${k.is_premium ? 'badge--premium' : 'badge--free'}">${k.is_premium ? 'Premium' : 'Free'}</span></td>
                <td>${k.expiry_ms ? new Date(k.expiry_ms).toLocaleDateString('ru-RU') : '∞'}</td>
                <td>${k.active ? '<span style="color:var(--color-mint-signal)">Active</span>' : '<span style="color:var(--color-slate-300)">Inactive</span>'}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>`;
    }
  } catch (e) {
    console.error('Admin load error:', e);
  }
}

async function togglePremium(telegramId, isPremium) {
  try {
    const resp = await fetch(`/api/admin/users/${telegramId}/premium`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_premium: isPremium }),
    });
    if (resp.ok) {
      showToast(isPremium ? 'Premium активирован' : 'Premium убран');
      loadAdminData();
    }
  } catch (e) {
    showToast('Ошибка');
  }
}

// ── Tutorials / FAQ toggles ─────────────────────────────

function toggleTutorial(el) {
  el.classList.toggle('open');
}

function toggleFaq(el) {
  el.classList.toggle('open');
}

// ── Helpers ─────────────────────────────────────────────

function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function showToast(message) {
  const existing = document.querySelector('.toast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.textContent = message;
  document.body.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(20px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

function formatBytes(b) {
  if (b === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (Math.abs(b) >= 1024 && i < units.length - 1) { b /= 1024; i++; }
  return b.toFixed(1) + ' ' + units[i];
}
