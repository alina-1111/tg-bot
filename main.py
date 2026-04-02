import telebot
from telebot import types
import psycopg2
import os
import threading
from flask import Flask

# ================== WEB (ДЛЯ RENDER) ==================

app = Flask(__name__)


@app.route("/")
def home():
    return "Bot is running!"


def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ================== БАЗА ДАННЫХ ==================


class DatabaseManager:
    def __init__(self):
        try:
            self.conn = psycopg2.connect(
                dbname=os.getenv("DB_NAME"),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASSWORD"),
                host=os.getenv("DB_HOST"),
                port=os.getenv("DB_PORT")
            )
            self.cursor = self.conn.cursor()
            print("✅ Подключение к БД успешно")
        except Exception as e:
            print("❌ Ошибка подключения к БД:", e)

    def get_models(self):
        self.cursor.execute("SELECT id, name FROM shoes")
        return self.cursor.fetchall()

    def get_model_details(self, model_id):
        self.cursor.execute("""
        SELECT brand, category, name, price
        FROM shoes
        WHERE id = %s
        """, (model_id,))
        return self.cursor.fetchone()

    def add_delivery(self, shoe_id, size_id, store_id, qty):
        try:
            self.cursor.execute("""
            INSERT INTO deliveries (shoe_id, size_id, store_id, quantity)
            VALUES (%s, %s, %s, %s)
            """, (shoe_id, size_id, store_id, qty))
            self.conn.commit()
        except Exception as e:
            print(e)
            self.conn.rollback()

    def add_sale(self, shoe_id, size_id, store_id, qty):
        try:
            self.cursor.execute("""
            INSERT INTO sales (shoe_id, size_id, store_id, quantity)
            VALUES (%s, %s, %s, %s)
            """, (shoe_id, size_id, store_id, qty))
            self.conn.commit()
        except Exception as e:
            print(e)
            self.conn.rollback()

    def get_stock(self):
        self.cursor.execute("SELECT * FROM current_stock LIMIT 20")
        return self.cursor.fetchall()

    def close(self):
        self.cursor.close()
        self.conn.close()

    def get_stores(self):
        self.cursor.execute("SELECT id, name FROM stores")
        return self.cursor.fetchall()
# ================== БОТ ==================


TOKEN = os.getenv("TOKEN")
ADMIN_ID = 880769222

bot = telebot.TeleBot(TOKEN)
db = DatabaseManager()

# ================== START ==================


@bot.message_handler(commands=['start'])
def start(message):
    if message.from_user.id == ADMIN_ID:
        admin_menu(message)
    else:
        user_menu(message)

# ================== МЕНЮ ==================


def user_menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('Каталог')
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)


def admin_menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('Добавить поступление', 'Добавить продажу')
    markup.add('Смотреть остатки')
    bot.send_message(message.chat.id, "Админ-панель:", reply_markup=markup)

# ================== КАТАЛОГ ==================


@bot.message_handler(func=lambda m: m.text == 'Каталог')
def catalog(message):
    models = db.get_models()

    text = "Модели:\n\n"
    for i, m in enumerate(models[:10], start=1):
        text += f"{i}. {m[1]}\n"

    bot.send_message(message.chat.id, text)

    bot.register_next_step_handler(message, select_model, models)


def select_model(message, models):
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Введите номер")
        return

    index = int(message.text) - 1

    if index < 0 or index >= len(models):
        bot.send_message(message.chat.id, "Неверный номер")
        return  # ✅ ВАЖНО: return должен быть здесь

    model = models[index]
    details = db.get_model_details(model[0])

    if details:
        text = (
            f"Бренд: {details[0]}\n"
            f"Категория: {details[1]}\n"
            f"Название: {details[2]}\n"
            f"Цена: {details[3]}"
        )
        bot.send_message(message.chat.id, text)  # ✅ внутри if
    else:
        bot.send_message(message.chat.id, "Не найдено ❌")


# ================== АДМИН ==================

@bot.message_handler(func=lambda m: m.text == 'Добавить поступление')
def add_delivery(message):
    if message.from_user.id != ADMIN_ID:
        return

    stores = db.get_stores()

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for s in stores:
        markup.add(f"{s[0]} | {s[1]}")

    msg = bot.send_message(message.chat.id, "Выбери магазин:", reply_markup=markup)
    bot.register_next_step_handler(msg, select_store_delivery)


# ================== ВЫБОР МАГАЗИНА ==================
def select_store_delivery(message):
    try:
        store_id = int(message.text.split('|')[0])
    except:
        bot.send_message(message.chat.id, "Ошибка выбора")
        return

    models = db.get_models()

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for m in models[:20]:
        markup.add(f"{m[0]} | {m[1]}")

    msg = bot.send_message(message.chat.id, "Выбери модель:", reply_markup=markup)
    bot.register_next_step_handler(msg, select_model_delivery, store_id)


# ================== ВЫБОР МОДЕЛИ ==================
def select_model_delivery(message, store_id):
    try:
        shoe_id = int(message.text.split('|')[0])
    except:
        bot.send_message(message.chat.id, "Ошибка выбора")
        return

    msg = bot.send_message(message.chat.id, "Введите размер:")
    bot.register_next_step_handler(msg, input_size_delivery, store_id, shoe_id)


# ================== ВЫБОР РАЗМЕРА ==================
def input_size_delivery(message, store_id, shoe_id):
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Введите число")
        return

    size = int(message.text)

    msg = bot.send_message(message.chat.id, "Введите количество:")
    bot.register_next_step_handler(msg, input_quantity_delivery, store_id, shoe_id, size)


# ================== КОЛИЧЕСТВО + СОХРАНЕНИЕ ==================
def input_quantity_delivery(message, store_id, shoe_id, size):
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Введите число")
        return

    qty = int(message.text)

    try:
        db.add_delivery(shoe_id, size, store_id, qty)

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("Добавить ещё", "В меню")

        bot.send_message(
            message.chat.id,
            "✅ Поступление добавлено",
            reply_markup=markup
        )

    except Exception as e:
        print(e)
        bot.send_message(message.chat.id, "Ошибка ❌")


# ================== ДОБАВИТЬ ЕЩЕ ==================
@bot.message_handler(func=lambda m: m.text == "Добавить ещё")
def add_more(message):
    add_delivery(message)


def process_delivery(message):
    try:
        shoe_id, size_id, store_id, qty = map(int, message.text.split())
        db.add_delivery(shoe_id, size_id, store_id, qty)
        bot.send_message(message.chat.id, "✅ Поступление добавлено")
    except Exception as e:
        print(e)
        bot.send_message(message.chat.id, "Ошибка ввода ❌")


@bot.message_handler(func=lambda m: m.text == 'Добавить продажу')
def add_sale(message):
    if message.from_user.id != ADMIN_ID:
        return
    msg = bot.send_message(message.chat.id,
                           "Введите: shoe_id size_id store_id quantity")
    bot.register_next_step_handler(msg, process_sale)


def process_sale(message):
    try:
        shoe_id, size_id, store_id, qty = map(int, message.text.split())
        db.add_sale(shoe_id, size_id, store_id, qty)
        bot.send_message(message.chat.id, "✅ Продажа добавлена")
    except Exception as e:
        print(e)
        bot.send_message(message.chat.id, "Ошибка ❌")


@bot.message_handler(func=lambda m: m.text == 'Смотреть остатки')
def stock(message):
    if message.from_user.id != ADMIN_ID:
        return
    rows = db.get_stock()
    text = "Остатки:\n\n"
    for r in rows:
        text += f"Модель {r[0]}, размер {r[1]}, магазин {r[2]}: {r[3]}\n"

    bot.send_message(message.chat.id, text)

# ================== ЗАПУСК ==================


if __name__ == "__main__":
    print("🚀 Бот запущен...")

    # ✅ всё должно быть ВНУТРИ if
    threading.Thread(target=run_web).start()

    bot.infinity_polling()
