import telebot
import json
import time
import requests
import asyncio
import os
import threading
import queue
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telethon import TelegramClient
from telethon.errors import UsernameNotOccupiedError, UsernameInvalidError, FloodWaitError
from telethon.tl.types import User, Channel

# Конфигурация бота
TOKEN = '7666642700:AAH57kVjKUNm-z-TY1qAOYnLD-Ss36GICrU'
CHANNEL_ID = -1002545464089
CHANNEL_LINK = 'https://t.me/+h0pdnThV7X8yZTMy'
ONLYSQ_API_URL = 'https://api.onlysq.ru/ai/v2'
ONLYSQ_MODEL = 'gpt-4o-mini'

# Конфигурация Telethon (замените на ваши данные)
API_ID = 17349  # Замените на ваш API ID
API_HASH = '344583e45741c457fe1862106095a5eb'  
SESSION_FILE = 'bot_session'


bot = telebot.TeleBot(TOKEN)
client = None
telethon_queue = queue.Queue()
response_queue = queue.Queue()
telethon_thread = None

class TelethonWorker:
    def __init__(self):
        self.client = None
        self.loop = None
        
    async def init_client(self):
        """Инициализация Telethon клиента"""
        self.client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
        
        if not os.path.exists(f'{SESSION_FILE}.session'):
            print("Файл сессии не найден. Необходимо войти в аккаунт.")
            await self.client.start()
            print("Вход в аккаунт выполнен успешно!")
        else:
            await self.client.start()
            print("Сессия загружена успешно!")
    
    async def get_user_info(self, username, request_id):
        """Получение информации о пользователе по username"""
        try:
            # Убираем @ если есть
            if username.startswith('@'):
                username = username[1:]
            
            # Получаем информацию о пользователе
            entity = await self.client.get_entity(username)
            
            if isinstance(entity, User):
                user_id = entity.id
                nickname = f"@{entity.username}" if entity.username else f"{entity.first_name or ''} {entity.last_name or ''}".strip()
                has_premium = getattr(entity, 'premium', False)
                
                result = {
                    'success': True,
                    'id': user_id,
                    'nickname': nickname,
                    'premium': has_premium,
                    'type': 'user'
                }
            elif isinstance(entity, Channel):
                result = {
                    'success': True,
                    'id': entity.id,
                    'nickname': f"@{entity.username}" if entity.username else entity.title,
                    'premium': False,
                    'type': 'channel'
                }
            else:
                result = {'success': False, 'error': 'Неизвестный тип сущности'}
                
        except (UsernameNotOccupiedError, UsernameInvalidError):
            result = {'success': False, 'error': 'invalid_username'}
        except FloodWaitError as e:
            result = {'success': False, 'error': f'flood_wait_{e.seconds}'}
        except Exception as e:
            print(f"Ошибка при получении информации о пользователе: {e}")
            result = {'success': False, 'error': 'unknown_error'}
        
        # Отправляем результат обратно
        response_queue.put((request_id, result))
    
    async def run(self):
        """Основной цикл обработки запросов"""
        await self.init_client()
        print("Telethon worker запущен!")
        
        while True:
            try:
                # Проверяем очередь запросов
                try:
                    request_type, username, request_id = telethon_queue.get(timeout=1)
                    if request_type == 'get_user_info':
                        await self.get_user_info(username, request_id)
                    elif request_type == 'stop':
                        break
                except queue.Empty:
                    continue
                except Exception as e:
                    print(f"Ошибка в Telethon worker: {e}")
                    response_queue.put((request_id, {'success': False, 'error': 'worker_error'}))
            except Exception as e:
                print(f"Критическая ошибка в Telethon worker: {e}")
                time.sleep(1)
        
        if self.client:
            await self.client.disconnect()
        print("Telethon worker остановлен!")

def start_telethon_worker():
    """Запуск Telethon worker в отдельном потоке"""
    def run_worker():
        worker = TelethonWorker()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(worker.run())
        finally:
            loop.close()
    
    thread = threading.Thread(target=run_worker, daemon=True)
    thread.start()
    return thread

def get_user_info_sync(username, timeout=30):
    """Синхронная функция для получения информации о пользователе"""
    request_id = f"{username}_{time.time()}"
    
    # Отправляем запрос в Telethon worker
    telethon_queue.put(('get_user_info', username, request_id))
    
    # Ждем ответ
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response_request_id, result = response_queue.get(timeout=1)
            if response_request_id == request_id:
                return result
        except queue.Empty:
            continue
    
    return {'success': False, 'error': 'timeout'}

def generate_support_response(username, evidence):
    prompt = (
        f"Составь краткий профессиональный ответ поддержки Telegram (не более 30 слов) "
        f"о пользователе @{username} на основании этих доказательств: {evidence}. "
        "Ответ должен быть вежливым, соответствовать правилам Telegram и предлагать дальнейшие действия."
    )
    
    payload = {
        "model": ONLYSQ_MODEL,
        "request": {
            "messages": [
                {
                    "role": "system",
                    "content": "Ты профессиональный помощник поддержки Telegram. Формулируй ответы кратко и по делу."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }
    }
    
    try:
        response = requests.post(ONLYSQ_API_URL, json=payload)
        if response.status_code == 200:
            data = response.json()
            return data['choices'][0]['message']['content']
    except Exception as e:
        print(f"API Error: {e}")
    
    return f"Мы рассмотрим вашу жалобу на @{username} и примем соответствующие меры."

def load_data():
    try:
        with open('data.json', 'r') as f:
            return json.load(f)
    except:
        return {'users': {}, 'reports': {}}

def save_data(data):
    with open('data.json', 'w') as f:
        json.dump(data, f)

def is_subscribed(user_id):
    try:
        status = bot.get_chat_member(CHANNEL_ID, user_id).status
        return status in ['member', 'administrator', 'creator']
    except:
        return False

@bot.message_handler(commands=['start'])
def start_command(message):
    data = load_data()
    user_id = str(message.from_user.id)
    
    if user_id not in data['users']:
        data['users'][user_id] = {
            'subscribed': False,
            'nick_verified': False,
            'last_report_time': 0
        }
        save_data(data)
    
    user_data = data['users'][user_id]
    
    if not user_data['subscribed']:
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("Канал", url=CHANNEL_LINK))
        markup.row(InlineKeyboardButton("Проверить", callback_data='check_subscription'))
        
        bot.send_message(
            message.chat.id,
            "‼️ <b>Вы не подписаны на канал</b>",
            parse_mode='HTML',
            reply_markup=markup
        )
    elif not user_data['nick_verified']:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("Проверить", callback_data='check_nick'))
        
        bot.send_message(
            message.chat.id,
            "<b>‼️ Чтоб использовать бота</b>\n\n"
            "<blockquote>Поставь в ник преписку @FatePizza_Bot</blockquote>\n"
            "<blockquote>Поставьте в описание юз нашего бота @FatePizza_Bot</blockquote>\n\n"
            "<b>Мы вынуждены применить такие меры так как бот бесплатный !</b>",
            parse_mode='HTML',
            reply_markup=markup
        )
    else:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("Сообщить", callback_data='report'))
        
        bot.send_message(
            message.chat.id,
            "<b>👋 Добро пожаловать в Fate Pizza</b>\n\n"
            "<blockquote>Данный бот поможет сообщить о нарушители и Fate Pizza вам поможет</blockquote>",
            parse_mode='HTML',
            reply_markup=markup
        )

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    data = load_data()
    user_id = str(call.from_user.id)
    
    if user_id not in data['users']:
        data['users'][user_id] = {
            'subscribed': False,
            'nick_verified': False,
            'last_report_time': 0
        }
    
    if call.data == 'check_subscription':
        if is_subscribed(call.from_user.id):
            data['users'][user_id]['subscribed'] = True
            save_data(data)
            
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("Проверить", callback_data='check_nick'))
            
            bot.edit_message_text(
                "<b>‼️ Чтоб использовать бота</b>\n\n"
                "<blockquote>Поставь в ник преписку @FatePizza_Bot</blockquote>\n"
                "<blockquote>Поставьте в описание юз нашего бота @FatePizza_Bot</blockquote>\n\n"
                "<b>Мы вынуждены применить такие меры так как бот бесплатный !</b>",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML',
                reply_markup=markup
            )
        else:
            bot.answer_callback_query(call.id, "❌ Вы всё ещё не подписаны!")
    
    elif call.data == 'check_nick':
        username = call.from_user.username or ''
        first_name = call.from_user.first_name or ''
        last_name = call.from_user.last_name or ''
        
        if '@FatePizza_Bot' in username or '@FatePizza_Bot' in first_name or '@FatePizza_Bot' in last_name:
            data['users'][user_id]['nick_verified'] = True
            save_data(data)
            
            bot.edit_message_text(
                "✅ <b>Вы выполнили все условия пропишите команду /start заного</b>",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML'
            )
        else:
            bot.answer_callback_query(call.id, "❌ В вашем нике не найдена преписка!")
    
    elif call.data == 'report':
        current_time = time.time()
        last_report = data['users'][user_id]['last_report_time']
        
        if current_time - last_report < 1800:
            remaining_seconds = 1800 - (current_time - last_report)
            remaining_minutes = (remaining_seconds + 59) // 60
            
            bot.answer_callback_query(
                call.id, 
                f"⏳ Вы сможете отправить следующую жалобу через {remaining_minutes} минут"
            )
            return
        
        msg = bot.edit_message_text(
            "Введите юзернейм человека или ссылку на канал (например: @username или t.me/username)",
            call.message.chat.id,
            call.message.message_id
        )
        bot.register_next_step_handler(msg, process_entity)

def process_entity(message):
    # Извлекаем username из различных форматов
    text = message.text.strip()
    if text.startswith('@'):
        entity = text[1:]
    elif 't.me/' in text:
        entity = text.split('t.me/')[-1].split('/')[0]
    else:
        entity = text
    
    # Отправляем сообщение о проверке
    checking_msg = bot.send_message(
        message.chat.id,
        "🔍 <b>Проверяю пользователя...</b>",
        parse_mode='HTML'
    )
    
    try:
        # Проверяем пользователя через Telethon
        user_info = get_user_info_sync(entity)
        
        # Удаляем сообщение о проверке
        bot.delete_message(message.chat.id, checking_msg.message_id)
        
        if not user_info['success']:
            if user_info['error'] == 'invalid_username':
                bot.send_message(
                    message.chat.id,
                    "❌ <b>Данный пользователь не зарегистрирован в телеграмм, попробуйте снова через 30 минут!</b>",
                    parse_mode='HTML'
                )
                return
            elif user_info['error'].startswith('flood_wait_'):
                wait_time = user_info['error'].split('_')[-1]
                bot.send_message(
                    message.chat.id,
                    f"⏳ <b>Слишком много запросов. Попробуйте через {wait_time} секунд.</b>",
                    parse_mode='HTML'
                )
                return
            elif user_info['error'] == 'timeout':
                bot.send_message(
                    message.chat.id,
                    "⏳ <b>Превышено время ожидания. Попробуйте позже.</b>",
                    parse_mode='HTML'
                )
                return
            else:
                bot.send_message(
                    message.chat.id,
                    "❌ <b>Произошла ошибка при проверке пользователя. Попробуйте позже.</b>",
                    parse_mode='HTML'
                )
                return
        
        # Если пользователь найден, запрашиваем доказательства
        msg = bot.send_message(
            message.chat.id,
            "✅ <b>Пользователь найден!</b>\n\nВведите причину и доказательства (кратко, 1-2 предложения)",
            parse_mode='HTML'
        )
        bot.register_next_step_handler(
            msg, 
            lambda m: process_reason(m, entity, user_info)
        )
        
    except Exception as e:
        # Удаляем сообщение о проверке в случае ошибки
        try:
            bot.delete_message(message.chat.id, checking_msg.message_id)
        except:
            pass
        
        print(f"Ошибка при обработке entity: {e}")
        bot.send_message(
            message.chat.id,
            "❌ <b>Произошла ошибка. Попробуйте позже.</b>",
            parse_mode='HTML'
        )

def process_reason(message, entity, user_info):
    data = load_data()
    user_id = str(message.from_user.id)
    
    # Генерация ответа поддержки
    support_response = generate_support_response(entity, message.text)
    
    # Сохраняем время отправки
    data['users'][user_id]['last_report_time'] = time.time()
    
    # Сохраняем жалобу
    report_id = len(data['reports']) + 1
    data['reports'][report_id] = {
        'user_id': user_id,
        'entity': entity,
        'reason': message.text,
        'response': support_response,
        'timestamp': time.time(),
        'target_info': user_info
    }
    save_data(data)
    
    # Формируем ответ с информацией о пользователе
    premium_status = "Да" if user_info.get('premium', False) else "Нет"
    
    response_text = (
        f"<b>📨 Ответ поддержки:</b>\n\n"
        f"<blockquote>Айди: {user_info['id']}\n"
        f"Никнейм: {user_info['nickname']}\n"
        f"Телеграм премиум - {premium_status}</blockquote>\n\n"
        f"{support_response}\n\n"
        f"<i>Жалоба на @{entity} зарегистрирована</i>"
    )
    
    bot.send_message(
        message.chat.id,
        response_text,
        parse_mode='HTML'
    )

def main():
    """Главная функция для запуска бота"""
    global telethon_thread
    
    # Проверяем наличие API данных
    if API_ID == 'YOUR_API_ID' or API_HASH == 'YOUR_API_HASH':
        print("❌ ОШИБКА: Необходимо указать API_ID и API_HASH!")
        print("Получите их на https://my.telegram.org")
        return
    
    print("🚀 Запуск бота с интеграцией Telethon...")
    
    # Проверяем токен бота
    try:
        test_bot = telebot.TeleBot(TOKEN)
        test_bot.get_me()
        print("✅ Токен бота валиден")
    except Exception as e:
        if "409" in str(e):
            print("❌ КРИТИЧЕСКАЯ ОШИБКА: Бот уже запущен в другом процессе!")
            print("Остановите все другие экземпляры бота перед запуском.")
            return
        else:
            print(f"❌ Ошибка токена бота: {e}")
            return
    
    # Запускаем Telethon worker
    print("Запуск Telethon worker...")
    telethon_thread = start_telethon_worker()
    
    # Ждем инициализации Telethon
    time.sleep(3)
    
    print("Запуск Telegram бота...")
    
    # Запускаем бота с обработкой ошибок
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except KeyboardInterrupt:
        print("\n⏹️ Остановка бота...")
    except Exception as e:
        if "409" in str(e):
            print("❌ Ошибка 409: Другой экземпляр бота уже запущен!")
            print("Остановите другие экземпляры бота и попробуйте снова.")
        else:
            print(f"❌ Ошибка бота: {e}")
    finally:
        # Останавливаем Telethon worker
        print("Остановка Telethon worker...")
        telethon_queue.put(('stop', None, None))
        if telethon_thread:
            telethon_thread.join(timeout=5)
        print("✅ Бот остановлен")

if __name__ == '__main__':
    main()
