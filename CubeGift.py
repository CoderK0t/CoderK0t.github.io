import logging
import os
import json
import hmac
import hashlib
import time
from typing import Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, LabeledPrice
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters, PreCheckoutQueryHandler

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = "8341085900:AAEarWlWJqLfVLzLpLw3ZGopuD812o78g0Q"
MINI_APP_URL = "https://coderk0t.github.io/"
PROVIDER_TOKEN = os.getenv('TELEGRAM_STARS_PROVIDER_TOKEN', 'TEST_PROVIDER_TOKEN')  # Получить у @BotFather

# Временное хранилище (в продакшене используйте БД)
user_balances = {}
payment_verifications = {}

def verify_telegram_init_data(init_data: str, bot_token: str) -> bool:
    """Верификация данных инициализации Telegram"""
    try:
        parsed_data = dict(param.split('=') for param in init_data.split('&'))
        hash_str = parsed_data.pop('hash', '')
        
        data_check_string = '\n'.join(
            f"{key}={value}" for key, value in sorted(parsed_data.items())
        )
        
        secret_key = hmac.new(
            key=b"WebAppData",
            msg=bot_token.encode(),
            digestmod=hashlib.sha256
        ).digest()
        
        calculated_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode(),
            digestmod=hashlib.sha256
        ).hexdigest()
        
        return calculated_hash == hash_str
    except Exception as e:
        logger.error(f"Verification error: {e}")
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user

    keyboard = [
        [InlineKeyboardButton("🎁 Играть и выигрывать!", web_app=WebAppInfo(url=MINI_APP_URL))],
        [InlineKeyboardButton("💰 Мой баланс", callback_data="balance")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_html(
        f"<b>🎲 CubeGift</b>\n\n"
        f"Привет, {user.mention_html()}! 👋\n\n"
        f"<b>Твоя игровая платформа с призами</b> 🎁\n\n"
        f"• Играй и выигрывай крутые подарки\n"
        f"• Пополняй баланс Telegram Stars\n"
        f"• Мгновенные выплаты и безопасность\n\n"
        f"<b>Нажми кнопку ниже чтобы начать! 👇</b>",
        reply_markup=reply_markup
    )

async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик данных из Mini App"""
    try:
        if not update.message or not update.message.web_app_data:
            return

        web_app_data = update.message.web_app_data
        data = json.loads(web_app_data.data)
        user = update.effective_user
        
        logger.info(f"Received data from {user.id}: {data}")

        # Обработка платежного запроса
        if data.get('type') == 'payment':
            await process_payment_request(update, data, user, context)
        elif data.get('type') == 'balance_request':
            await send_balance_update(user.id)
        else:
            await update.message.reply_text("🎉 Данные получены! Обрабатываем вашу операцию...")

    except Exception as e:
        logger.error(f"Error processing web app data: {e}")
        await update.message.reply_text("❌ Ошибка обработки данных")

async def process_payment_request(update: Update, data: Dict[str, Any], user, context):
    """Обработка запроса на оплату"""
    amount = data.get('amount', 100)
    
    # Создание инвойса в Telegram Stars
    title = "🎮 Пополнение баланса CubeGift"
    description = f"Пополнение на {amount} игровых единиц"
    payload = f"stars_{amount}_{user.id}_{int(time.time())}"
    
    prices = [LabeledPrice("Игровая валюта", amount)]
    
    try:
        # Отправка инвойса
        await context.bot.send_invoice(
            chat_id=user.id,
            title=title,
            description=description,
            payload=payload,
            provider_token=PROVIDER_TOKEN,
            currency="XTR",  # Валюта Telegram Stars
            prices=prices,
            need_name=False,
            need_phone_number=False,
            need_email=False,
            need_shipping_address=False,
            is_flexible=False,
            max_tip_amount=1000,
            suggested_tip_amounts=[100, 300, 500],
            start_parameter=f"cube_gift_{amount}"
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
        await update.message.reply_text("❌ Ошибка создания счета. Попробуйте позже.")

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение возможности оплаты"""
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка успешного платежа"""
    payment = update.message.successful_payment
    user_id = update.effective_user.id
    
    try:
        # Извлекаем данные из payload
        payload_parts = payment.invoice_payload.split('_')
        if len(payload_parts) >= 4:
            amount = int(payload_parts[1])
            target_user_id = int(payload_parts[2])
            
            # Верифицируем платеж
            if payment_verifications.get(payment.invoice_payload):
                # Обновляем баланс
                user_balances[user_id] = user_balances.get(user_id, 0) + amount
                
                await update.message.reply_html(
                    f"🎉 <b>Платеж успешен!</b>\n\n"
                    f"Ваш баланс пополнен на <b>{amount}</b> единиц\n"
                    f"ID транзакции: <code>{payment.telegram_payment_charge_id}</code>\n\n"
                    f"Текущий баланс: <b>{user_balances[user_id]}</b> единиц\n\n"
                    f"Возвращайтесь в игру чтобы использовать свои средства! 🎮"
                )
                
                # Удаляем из временного хранилища
                del payment_verifications[payment.invoice_payload]
                
                logger.info(f"Payment successful for user {user_id}, amount: {amount}")
            else:
                await update.message.reply_text("❌ Ошибка верификации платежа")
        else:
            await update.message.reply_text("✅ Платеж получен")
            
    except Exception as e:
        logger.error(f"Payment processing error: {e}")
        await update.message.reply_text("❌ Ошибка обработки платежа")

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда проверки баланса"""
    user_id = update.effective_user.id
    balance = user_balances.get(user_id, 0)
    
    keyboard = [
        [InlineKeyboardButton("💰 Пополнить баланс", web_app=WebAppInfo(url=MINI_APP_URL))],
        [InlineKeyboardButton("🎮 Открыть игру", web_app=WebAppInfo(url=MINI_APP_URL))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_html(
        f"💰 <b>Ваш баланс:</b> {balance} единиц\n\n"
        f"Для пополнения используйте Mini App или команду /buy <i>количество</i>",
        reply_markup=reply_markup
    )

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда покупки валюты"""
    try:
        amount = int(context.args[0]) if context.args and context.args[0].isdigit() else 100
        
        if amount < 10:
            await update.message.reply_text("❌ Минимальная сумма пополнения: 10 единиц")
            return
            
        await process_payment_request(update, {'amount': amount, 'currency': 'stars'}, update.effective_user, context)
        
    except (IndexError, ValueError):
        await update.message.reply_text("Используйте: /buy <количество> (минимум 10)")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на inline кнопки"""
    query = update.callback_query
    await query.answer()

    if query.data == "balance":
        user_id = query.from_user.id
        balance = user_balances.get(user_id, 0)
        await query.edit_message_text(f"💰 Ваш баланс: {balance} единиц")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    if not update.message:
        return

    keyboard = [
        [InlineKeyboardButton("🎁 Играть и выигрывать!", web_app=WebAppInfo(url=MINI_APP_URL))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = update.message.text.lower()

    if any(word in text for word in ['привет', 'hello', 'hi', 'start', 'игра', 'game']):
        await update.message.reply_html(
            "🎲 <b>CubeGift</b>\n\n"
            "Привет! Готов выигрывать подарки? 🎁\n\n"
            "Пополняй баланс Telegram Stars и начинай играть!\n\n"
            "Жми на кнопку ниже 👇",
            reply_markup=reply_markup
        )
    elif any(word in text for word in ['баланс', 'balance', 'деньги', 'money', 'stars']):
        await balance_command(update, context)
    else:
        await update.message.reply_html(
            "🎲 <b>CubeGift</b>\n\n"
            "Не понял тебя... 😕\n\n"
            "Хочешь выиграть крутые подарки? 🎁\n"
            "Пополняй баланс Stars и начинай играть! 👇",
            reply_markup=reply_markup
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Exception while handling an update: {context.error}")

def main():
    """Основная функция запуска бота"""
    application = Application.builder().token(BOT_TOKEN).build()

    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("buy", buy_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Добавляем обработчик ошибок
    application.add_error_handler(error_handler)

    # Запускаем бота
    print("🎲 CubeGift бот запущен с полной платежной системой")
    print("💰 Используется Telegram Stars (XTR)")
    print("🌐 Web App URL:", MINI_APP_URL)
    print("Ожидание сообщений...")
    
    application.run_polling()

if __name__ == "__main__":
    main()