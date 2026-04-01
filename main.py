import telebot
from telebot import types
import psycopg2


# ================== БАЗА ДАННЫХ ==================
class DatabaseManager:
    def __init__(self):
        self.conn = psycopg2.connect(
            dbname="shoes",
            user="postgres",
            password="12345",  # поменяй на свой пароль
            host="localhost",
            port="5432"
        )
        self.cursor = self.conn.cursor()

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
        self.cursor.execute("""
            INSERT INTO deliveries (shoe_id, size_id, store_id, quantity)
            VALUES (%s, %s, %s, %s)
        """, (shoe_id, size_id, store_id, qty))
        self.conn.commit()

    def add_sale(self, shoe_id, size_id, store_id, qty):
        self.cursor.execute("""
            INSERT INTO sales (shoe_id, size_id, store_id, quantity)
            VALUES (%s, %s, %s, %s)
        """, (shoe_id, size_id, store_id, qty))
        self.conn.commit()

    def get_stock(self):
        self.cursor.execute("SELECT * FROM current_stock LIMIT 20")
        return self.cursor.fetchall()

    def close(self):
        self.cursor.close()
        self.conn.close()


# ================== БОТ ==================
TOKEN = '8380279768:AAEPKZUoqBB78R8eH-sfXBlJuCLszv2F5Jc'
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
    model = models[index]

    details = db.get_model_details(model[0])

    if details:
        text = (
            f"Бренд: {details[0]}\n"
            f"Категория: {details[1]}\n"
            f"Название: {details[2]}\n"
            f"Цена: {details[3]}"
        )
        bot.send_message(message.chat.id, text)


# ================== АДМИН ==================

# --- Добавить поступление ---
@bot.message_handler(func=lambda m: m.text == 'Добавить поступление')
def add_delivery(message):
    if message.from_user.id != ADMIN_ID:
        return

    msg = bot.send_message(message.chat.id,
                           "Введите: shoe_id size_id store_id quantity")
    bot.register_next_step_handler(msg, process_delivery)


def process_delivery(message):
    try:
        shoe_id, size_id, store_id, qty = map(int, message.text.split())
        db.add_delivery(shoe_id, size_id, store_id, qty)
        bot.send_message(message.chat.id, "✅ Поступление добавлено")
    except:
        bot.send_message(message.chat.id, "Ошибка ввода ❌")


# --- Добавить продажу ---
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
    except:
        bot.send_message(message.chat.id, "Ошибка ❌")


# --- Остатки ---
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
bot.infinity_polling()