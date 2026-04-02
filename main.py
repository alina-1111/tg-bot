import telebot
from telebot import types
import psycopg2
import os
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

    def get_size_id(self, size_value):
        try:
            self.conn.rollback()  # 🔥

            self.cursor.execute("""
                SELECT id FROM sizes
                WHERE size_value = %s
            """, (size_value,))

            result = self.cursor.fetchone()
            return result[0] if result else None

        except Exception as e:
            print("Ошибка размера:", e)
            self.conn.rollback()
            return None

    def safe_execute(self, query, params=None):
        try:
            self.conn.rollback()
            self.cursor.execute(query, params or ())
            return self.cursor.fetchall()
        except Exception as e:
            print("SQL ошибка:", e)
            self.conn.rollback()
            return []

    def get_deliveries_full(self):
        return self.safe_execute("""
            SELECT 
                d.id,
                s.name,
                sh.brand,
                sh.category,
                sh.name,
                sz.size_value,
                d.quantity,
                d.created_at
            FROM deliveries d
            JOIN stores s ON d.store_id = s.id
            JOIN shoes sh ON d.shoe_id = sh.id
            LEFT JOIN sizes sz ON d.size_id = sz.id
            ORDER BY d.created_at DESC
            LIMIT 10
        """)

    def get_deliveries_by_store(self, store_id):
        return self.safe_execute("""
            SELECT 
                s.name, sh.brand, sh.category, sh.name,
                sz.size_value, d.quantity, d.created_at
            FROM deliveries d
            JOIN stores s ON d.store_id = s.id
            JOIN shoes sh ON d.shoe_id = sh.id
            JOIN sizes sz ON d.size_id = sz.id
            WHERE s.id = %s
            ORDER BY d.created_at DESC
        """, (store_id,))

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
    markup.add('Смотреть поступления')  # 👈 ДОБАВЬ
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

    # сохраняем соответствие name -> id
    store_dict = {s[1]: s[0] for s in stores}

    for name in store_dict.keys():
        markup.add(name)

    msg = bot.send_message(message.chat.id, "Выбери магазин:", reply_markup=markup)
    bot.register_next_step_handler(msg, select_store_delivery, store_dict)


# ================== ВЫБОР МАГАЗИНА ==================
def select_store_delivery(message, store_dict):
    if message.text not in store_dict:
        bot.send_message(message.chat.id, "Выбери из списка")
        return

    store_id = store_dict[message.text]

    # ❗ убираем клавиатуру
    bot.send_message(message.chat.id, "Ок", reply_markup=types.ReplyKeyboardRemove())

    models = db.get_models()
    model_dict = {m[1]: m[0] for m in models}

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for name in list(model_dict.keys())[:20]:
        markup.add(name)

    msg = bot.send_message(message.chat.id, "Выбери модель:", reply_markup=markup)
    bot.register_next_step_handler(msg, select_model_delivery, store_id, model_dict)


# ================== ВЫБОР МОДЕЛИ ==================
def select_model_delivery(message, store_id, model_dict):
    if message.text not in model_dict:
        bot.send_message(message.chat.id, "Выбери из списка")
        return

    shoe_id = model_dict[message.text]

    # ❗ убираем клавиатуру
    bot.send_message(message.chat.id, "Ок", reply_markup=types.ReplyKeyboardRemove())

    msg = bot.send_message(
        message.chat.id,
        "Введи размеры и количество:\n\nПример:\n40 5\n41 3\n42 2"
    )

    bot.register_next_step_handler(msg, input_bulk_sizes, store_id, shoe_id)


# ================== ВВОД РАЗМЕРА И КОЛИЧЕСТВА ==================
def input_bulk_sizes(message, store_id, shoe_id):
    lines = message.text.split("\n")

    success = 0

    for line in lines:
        try:
            size_str, qty_str = line.split()

            size = float(size_str.replace(',', '.'))  # поддержка 39,5
            qty = int(qty_str)
            size_id = db.get_size_id(size)

            if not size_id:
                bot.send_message(message.chat.id, f"Размер {size} не найден ❌")
                return

            db.add_delivery(shoe_id, size_id, store_id, qty)
            success += 1
        except:
            continue

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Добавить ещё", "В меню")

    bot.send_message(
        message.chat.id,
        f"✅ Добавлено записей: {success}",
        reply_markup=markup
    )


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


@bot.message_handler(func=lambda m: m.text == 'Смотреть поступления')
def view_deliveries(message):
    if message.from_user.id != ADMIN_ID:
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('Последние', 'По магазину')
    markup.add('По модели', 'По дате')
    markup.add('В меню')

    bot.send_message(message.chat.id, "Выбери фильтр:", reply_markup=markup)


@bot.message_handler(func=lambda m: m.text and m.text.strip() == 'Последние')
def show_last_deliveries(message):
    rows = db.get_deliveries_full()

    text = "📦 Последние поступления:\n\n"

    for r in rows:
        part = (
            f"🏪 {r[1]}\n"
            f"👟 {r[2]} | {r[3]} | {r[4]}\n"
            f"📏 Размер: {r[5]}\n"
            f"📦 Кол-во: {r[6]}\n"
            f"📅 {r[7]}\n\n"
        )

        # 🔥 если превышает лимит — отправляем кусок
        if len(text) + len(part) > 4000:
            bot.send_message(message.chat.id, text)
            text = ""

        text += part

    if text:
        bot.send_message(message.chat.id, text)


@bot.message_handler(func=lambda m: m.text == 'По магазину')
def filter_store(message):
    stores = db.get_stores()

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    store_dict = {s[1]: s[0] for s in stores}

    for name in store_dict:
        markup.add(name)

    msg = bot.send_message(message.chat.id, "Выбери магазин:", reply_markup=markup)
    bot.register_next_step_handler(msg, show_by_store, store_dict)


def show_by_store(message, store_dict):
    if message.text not in store_dict:
        return

    store_id = store_dict[message.text]
    rows = db.get_deliveries_by_store(store_id)

    text = f"📦 Поступления ({message.text}):\n\n"

    for r in rows:
        text += (
            f"👟 {r[1]} | {r[2]} | {r[3]}\n"
            f"📏 {r[4]} | 📦 {r[5]}\n"
            f"📅 {r[6]}\n\n"
        )

    bot.send_message(message.chat.id, text)


@bot.message_handler(func=lambda m: m.text == 'По дате')
def filter_date(message):
    msg = bot.send_message(message.chat.id, "Введи дату (YYYY-MM-DD):")
    bot.register_next_step_handler(msg, show_by_date)


def show_by_date(message):
    date = message.text

    try:
        db.conn.rollback()  # 🔥 СБРОС

        rows = db.safe_execute("""
            SELECT s.name, sh.brand, sh.category, sh.name,
                   sz.size_value, d.quantity
            FROM deliveries d
            JOIN stores s ON d.store_id = s.id
            JOIN shoes sh ON d.shoe_id = sh.id
            JOIN sizes sz ON d.size_id = sz.id
            WHERE DATE(d.created_at) = %s
        """, (date,))

        text = f"📅 Поступления за {date}:\n\n"

        for r in rows:
            text += f"{r[0]} | {r[1]} {r[3]} | {r[4]} | {r[5]}\n"

        bot.send_message(message.chat.id, text)

    except Exception as e:
        print("Ошибка даты:", e)
        db.conn.rollback()  # 🔥 ВАЖНО
        bot.send_message(message.chat.id, "Ошибка ❌ Проверь формат даты")
# ================== ЗАПУСК ==================


if __name__ == "__main__":
    print("🚀 Бот запущен")
    bot.remove_webhook()
    bot.infinity_polling(skip_pending=True)
