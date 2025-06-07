import logging
import os
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

import qrcode
from PIL import Image, ImageColor
import io
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base

# === Настройки ===
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DB_URL = os.getenv("DATABASE_URL")

if not DB_URL:
    raise ValueError("DATABASE_URL не найден. Проверь переменные окружения!")

# === Цвета по умолчанию ===
COLORS = {
    "Чёрный на белом": ("black", "white"),
    "Красный на белом": ("red", "white"),
    "Синий на белом": ("blue", "white"),
    "Зелёный на белом": ("green", "white"),
    "Белый на чёрном": ("white", "black")
}

# === SQLAlchemy setup ===
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    user_id = Column(String, unique=True)
    name = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class QRHistory(Base):
    __tablename__ = 'history'
    id = Column(Integer, primary_key=True)
    user_id = Column(String)
    data = Column(Text)
    fill_color = Column(String)
    bg_color = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

engine = create_engine(DB_URL)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# === Клавиатуры ===

def main_keyboard():
    keyboard = [
        [InlineKeyboardButton("🆕 Создать QR-код", callback_data="create_qr")],
        [InlineKeyboardButton("📜 История", callback_data="show_history")],
        [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")],
        [InlineKeyboardButton("❤️ Поддержать создателя", callback_data="donate")]
    ]
    return InlineKeyboardMarkup(keyboard)

def back_to_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🏡 Главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_color_keyboard():
    keyboard = [
        [InlineKeyboardButton(text, callback_data=f"color|{fc}|{bc}")]
        for text, (fc, bc) in COLORS.items()
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(keyboard)


# === Универсальная функция для отправки сообщений с кнопкой "Главное меню" ===
async def send_with_main_menu(context: ContextTypes.DEFAULT_TYPE, update: Update, message: str):
    if update.message:
        await update.message.reply_text(message, reply_markup=back_to_menu_keyboard(), parse_mode='Markdown')
    elif update.callback_query:
        try:
            await update.callback_query.edit_message_text(message, reply_markup=back_to_menu_keyboard(), parse_mode='Markdown')
        except Exception:
            # Если это было фото — используем caption
            await update.callback_query.edit_message_caption(
                caption=message,
                reply_markup=back_to_menu_keyboard(),
                parse_mode='Markdown'
            )


# === Команда /start — только здесь показываем лого ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    session = Session()

    db_user = session.query(User).filter_by(user_id=str(user.id)).first()
    if not db_user:
        db_user = User(user_id=str(user.id), name=user.first_name)
        session.add(db_user)
        session.commit()

    welcome_text = f"""
👋 Привет, {user.first_name}!

Я — бот для создания QR-кодов. Вот что я умею:

Выберите действие ниже 👇
"""

    # Отправляем фото только один раз — при старте
    try:
        with open("logo.png", "rb") as photo_file:
            await update.message.reply_photo(
                photo=photo_file,
                caption=welcome_text,
                reply_markup=main_keyboard(),
                parse_mode='Markdown'
            )
    except FileNotFoundError:
        await update.message.reply_text(
            text=welcome_text,
            reply_markup=main_keyboard(),
            parse_mode='Markdown'
        )


# === Обработка нажатий на главные кнопки ===
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "create_qr":
        try:
            await query.edit_message_text(
                text="Выберите цвета:",
                reply_markup=get_color_keyboard()
            )
        except Exception:
            await query.edit_message_caption(
                caption="Выберите цвета:",
                reply_markup=get_color_keyboard()
            )

    elif query.data == "show_history":
        session = Session()
        history = session.query(QRHistory).filter_by(user_id=str(query.from_user.id)).order_by(QRHistory.created_at.desc()).limit(5).all()

        if history:
            msg = "📜 Ваша история последних 5 QR-кодов:\n\n"
            for item in history:
                msg += f"🔗 `{item.data}`\n🎨 {item.fill_color} | {item.bg_color}\n🕒 {item.created_at.strftime('%d.%m %H:%M')}\n\n"
        else:
            msg = "🚫 У вас пока нет истории."

        await send_with_main_menu(context, update, msg)

    elif query.data == "help":
        help_text = """
📝 Как использовать:

1. Нажмите "🆕 Создать QR-код".
2. Выберите цвета или оставьте стандартные.
3. Отправьте текст или ссылку.
4. Получите готовый QR-код 🎉

Вы также можете отправить PNG-изображение, чтобы добавить логотип внутрь QR-кода.
"""
        await send_with_main_menu(context, update, help_text)

    elif query.data == "donate":
        donate_text = """
❤️ Спасибо за поддержку!

Если тебе нравится этот бот, ты можешь поддержать меня:

- 💝 Сказать спасибо: @che1nov
- 💳 Перевести денежку: `2204 3101 7320 1438`

Любая помощь важна!
"""
        await send_with_main_menu(context, update, donate_text)

    elif query.data == "main_menu":
        welcome_text = """
👋 Привет!

Я — бот для создания QR-кодов. Вот что я умею:

Выберите действие ниже 👇
"""
        try:
            await query.edit_message_text(
                text=welcome_text,
                reply_markup=main_keyboard(),
                parse_mode='Markdown'
            )
        except Exception:
            await query.edit_message_caption(
                caption=welcome_text,
                reply_markup=main_keyboard(),
                parse_mode='Markdown'
            )


# === Обработка выбора цвета и возврата в меню ===
async def color_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("color"):
        _, fill_color, bg_color = query.data.split("|")
        context.user_data['fill_color'] = fill_color
        context.user_data['bg_color'] = bg_color

        msg = "✅ Цвет выбран. Отправьте текст для QR-кода."
        await send_with_main_menu(context, update, msg)

    elif query.data == "back_to_menu":
        welcome_text = """
👋 Привет!

Я — бот для создания QR-кодов. Вот что я умею:

Выберите действие ниже 👇
"""
        try:
            await query.edit_message_text(
                text=welcome_text,
                reply_markup=main_keyboard(),
                parse_mode='Markdown'
            )
        except Exception:
            await query.edit_message_caption(
                caption=welcome_text,
                reply_markup=main_keyboard(),
                parse_mode='Markdown'
            )


# === Функция генерации QR-кода в памяти (без записи в файл) ===
def generate_qr(data, fill_color="black", bg_color="white"):
    try:
        fill = ImageColor.getrgb(fill_color)
        background = ImageColor.getrgb(bg_color)
    except ValueError:
        return None

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    img = qr.make_image(fill_color=fill, back_color=background).convert("RGBA")
    byte_io = io.BytesIO()
    img.save(byte_io, 'PNG')
    byte_io.seek(0)
    return byte_io


# === Обработка текстовых сообщений (генерация QR) ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    session = Session()

    fill_color = context.user_data.get('fill_color', 'black')
    bg_color = context.user_data.get('bg_color', 'white')

    data = update.message.text
    if '|' in data:
        parts = data.split('|')
        data = parts[0]
        fill_color = parts[1] if len(parts) > 1 else fill_color
        bg_color = parts[2] if len(parts) > 2 else bg_color

    qr_image = generate_qr(data, fill_color, bg_color)

    if qr_image:
        history = QRHistory(
            user_id=str(user.id),
            data=data,
            fill_color=fill_color,
            bg_color=bg_color
        )
        session.add(history)
        session.commit()
        session.close()

        # Отправляем QR-код
        await update.message.reply_photo(
            photo=qr_image,
            caption="Вот ваш QR-код!",
            reply_markup=back_to_menu_keyboard()
        )

        # Автоматически возвращаем пользователя к стартовому меню
        await start(update, context)


# === Точка входа ===
if __name__ == '__main__':
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан в переменных окружения")

    if not DB_URL:
        raise ValueError("DATABASE_URL не найден в переменных окружения")

    logging.basicConfig(level=logging.INFO)
    app = ApplicationBuilder().token(TOKEN).build()

    # Хэндлеры
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler, pattern=r'^(create_qr|show_history|help|donate|main_menu)$'))
    app.add_handler(CallbackQueryHandler(color_button_handler, pattern=r'^(color|back_to_menu)'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Бот запущен...")
    app.run_polling()