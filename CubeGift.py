import logging
import os
import json
import time
from typing import Dict, Any

from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    Message, CallbackQuery, PreCheckoutQuery, 
    SuccessfulPayment, LabeledPrice, InlineKeyboardButton, 
    InlineKeyboardMarkup, WebAppInfo
)
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Статичные переменные (прямо в коде)
BOT_TOKEN = "8341085900:AAEarWlWJqLfVLzLpLw3ZGopuD812o78g0Q"
MINI_APP_URL = "https://coderk0t.github.io/"

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Временное хранилище (в продакшене используйте БД)
user_balances = {}
payment_verifications = {}

# Клавиатура основного меню
def get_main_keyboard():
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🎁 Играть и выигрывать!", web_app=WebAppInfo(url=MINI_APP_URL))
    keyboard.button(text="💰 Мой баланс", callback_data="balance")
    keyboard.adjust(1)
    return keyboard.as_markup()

# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user = message.from_user
    
    welcome_text = (
        f"<b>🎲 CubeGift</b>\n\n"
        f"Привет, {user.mention_html()}! 👋\n\n"
        f"<b>Твоя игровая платформа с призами</b> 🎁\n\n"
        f"• Играй и выигрывай крутые подарки\n"
        f"• Пополняй баланс Telegram Stars\n"
        f"• Мгновенные выплаты и безопасность\n\n"
        f"<b>Нажми кнопку ниже чтобы начать! 👇</b>"
    )
    
    await message.answer(welcome_text, reply_markup=get_main_keyboard())

# Обработчик данных из Mini App
@dp.message(F.web_app_data)
async def handle_web_app_data(message: Message):
    try:
        web_app_data = message.web_app_data
        data = json.loads(web_app_data.data)
        user = message.from_user
        
        logger.info(f"Received data from {user.id}: {data}")

        # Обработка платежного запроса
        if data.get('type') == 'payment':
            await process_payment_request(message, data, user)
        else:
            await message.answer("🎉 Данные получены! Обрабатываем вашу операцию...")

    except Exception as e:
        logger.error(f"Error processing web app data: {e}")
        await message.answer("❌ Ошибка обработки данных")

# Обработка запроса на оплату
async def process_payment_request(message: Message, data: Dict[str, Any], user: types.User):
    amount = data.get('amount', 100)
    
    # Создание инвойса в Telegram Stars
    title = "🎮 Пополнение баланса CubeGift"
    description = f"Пополнение на {amount} игровых единиц"
    payload = f"stars_{amount}_{user.id}_{int(time.time())}"
    
    prices = [LabeledPrice(label="Игровая валюта", amount=amount)]
    
    try:
        # Создаем клавиатуру с кнопкой оплаты
        builder = InlineKeyboardBuilder()
        builder.button(text=f"Оплатить {amount} ⭐", pay=True)
        
        # Отправка инвойса БЕЗ provider_token для Telegram Stars
        await message.answer_invoice(
            title=title,
            description=description,
            payload=payload,
            provider_token="",  # ПУСТАЯ СТРОКА для цифровых товаров
            currency="XTR",  # Валюта Telegram Stars
            prices=prices,
            max_tip_amount=1000,
            suggested_tip_amounts=[100, 300, 500],
            start_parameter=f"cube_gift_{amount}",
            reply_markup=builder.as_markup()
        )
        
        # Сохраняем информацию о платеже для верификации
        payment_verifications[payload] = {
            'user_id': user.id,
            'amount': amount,
            'timestamp': time.time()
        }
        
        logger.info(f"Invoice created for user {user.id}, amount: {amount}")
        
    except Exception as e:
        logger.error(f"Invoice creation error: {e}")
        await message.answer("❌ Ошибка создания счета. Попробуйте позже.")

# Подтверждение возможности оплаты
@dp.pre_checkout_query()
async def precheckout_callback(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

# Обработка успешного платежа
@dp.message(F.successful_payment)
async def successful_payment_callback(message: Message):
    payment = message.successful_payment
    user_id = message.from_user.id
    
    try:
        # Извлекаем данные из payload
        payload_parts = payment.invoice_payload.split('_')
        if len(payload_parts) >= 4:
            amount = int(payload_parts[1])
            
            # Верифицируем платеж
            if payment_verifications.get(payment.invoice_payload):
                # Обновляем баланс
                user_balances[user_id] = user_balances.get(user_id, 0) + amount
                
                success_text = (
                    f"🎉 <b>Платеж успешен!</b>\n\n"
                    f"Ваш баланс пополнен на <b>{amount}</b> единиц\n"
                    f"ID транзакции: <code>{payment.telegram_payment_charge_id}</code>\n\n"
                    f"Текущий баланс: <b>{user_balances[user_id]}</b> единиц\n\n"
                    f"Возвращайтесь в игру чтобы использовать свои средства! 🎮"
                )
                
                await message.answer(success_text)
                
                # Удаляем из временного хранилища
                del payment_verifications[payment.invoice_payload]
                
                logger.info(f"Payment successful for user {user_id}, amount: {amount}")
            else:
                await message.answer("❌ Ошибка верификации платежа")
        else:
            await message.answer("✅ Платеж получен")
            
    except Exception as e:
        logger.error(f"Payment processing error: {e}")
        await message.answer("❌ Ошибка обработки платежа")

# Команда проверки баланса
@dp.message(Command("balance"))
async def balance_command(message: Message):
    user_id = message.from_user.id
    balance = user_balances.get(user_id, 0)
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="💰 Пополнить баланс", web_app=WebAppInfo(url=MINI_APP_URL))
    keyboard.button(text="🎮 Открыть игру", web_app=WebAppInfo(url=MINI_APP_URL))
    keyboard.adjust(1)
    
    balance_text = (
        f"💰 <b>Ваш баланс:</b> {balance} единиц\n\n"
        f"Для пополнения используйте Mini App или команду /buy <i>количество</i>"
    )
    
    await message.answer(balance_text, reply_markup=keyboard.as_markup())

# Команда покупки валюты
@dp.message(Command("buy"))
async def buy_command(message: Message, command: CommandObject):
    try:
        if command.args is None:
            await message.answer("Используйте: /buy <количество> (минимум 10)")
            return
            
        amount = int(command.args)
        
        if amount < 1:
            await message.answer("❌ Минимальная сумма пополнения: 1 единиц")
            return
            
        await process_payment_request(message, {'amount': amount, 'currency': 'stars'}, message.from_user)
        
    except ValueError:
        await message.answer("Используйте: /buy <количество>")

# Обработчик нажатий на inline кнопки
@dp.callback_query(F.data == "balance")
async def balance_button_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    balance = user_balances.get(user_id, 0)
    await callback.answer()
    await callback.message.answer(f"💰 Ваш баланс: {balance} единиц")

# Обработчик текстовых сообщений
@dp.message(F.text)
async def handle_message(message: Message):
    text = message.text.lower()

    if any(word in text for word in ['привет', 'hello', 'hi', 'start', 'игра', 'game']):
        welcome_text = (
            "🎲 <b>CubeGift</b>\n\n"
            "Привет! Готов выигрывать подарки? 🎁\n\n"
            "Пополняй баланс Telegram Stars и начинай играть!\n\n"
            "Жми на кнопку ниже 👇"
        )
        await message.answer(welcome_text, reply_markup=get_main_keyboard())
    elif any(word in text for word in ['баланс', 'balance', 'деньги', 'money', 'stars']):
        await balance_command(message)
    else:
        default_text = (
            "🎲 <b>CubeGift</b>\n\n"
            "Не понял тебя... 😕\n\n"
            "Хочешь выиграть крутые подарки? 🎁\n"
            "Пополняй баланс Stars и начинай играть! 👇"
        )
        await message.answer(default_text, reply_markup=get_main_keyboard())

# Обработчик ошибок
@dp.error()
async def error_handler(event: types.ErrorEvent):
    logger.error(f"Exception while handling an update: {event.exception}")

# Функция запуска бота
async def main():
    logger.info("🎲 CubeGift бот запущен с полной платежной системой")
    logger.info("💰 Используется Telegram Stars (XTR)")
    logger.info("🌐 Web App URL: %s", MINI_APP_URL)
    logger.info("📝 Provider Token: НЕ ТРЕБУЕТСЯ для цифровых товаров")
    logger.info("Ожидание сообщений...")
    
    # Запускаем поллинг
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())