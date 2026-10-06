import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

# Забираем токен из настроек сервера (Environment Variables).
# Если переменная не задана, используется значение по умолчанию.
TOKEN = os.getenv("BOT_TOKEN", "8805517591:AAF0TqlI-SbGFu1RDEk89_OJ4isGVA__yKc")
DB = "schedule.db"

logging.basicConfig(level=logging.INFO)

dp = Dispatcher()


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        weekday INTEGER NOT NULL,
        lesson_num INTEGER NOT NULL,
        subject TEXT NOT NULL,
        UNIQUE(user_id, weekday, lesson_num)
    );

    CREATE TABLE IF NOT EXISTS homework (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        subject TEXT NOT NULL,
        task TEXT NOT NULL,
        due_date TEXT NOT NULL,
        done INTEGER NOT NULL DEFAULT 0
    );
    """)
    conn.commit()
    conn.close()


def menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Сегодня"), KeyboardButton(text="📚 Расписание")],
            [KeyboardButton(text="📝 Добавить ДЗ"), KeyboardButton(text="📋 ДЗ на завтра")],
            [KeyboardButton(text="✅ Выполнить ДЗ"), KeyboardButton(text="➕ Добавить урок")],
        ],
        resize_keyboard=True
    )


DAY_NAMES = {
    1: "Понедельник", 2: "Вторник", 3: "Среда",
    4: "Четверг", 5: "Пятница", 6: "Суббота", 7: "Воскресенье"
}


def next_day():
    d = datetime.now().date() + timedelta(days=1)
    return d, d.isoweekday()


@dp.message(CommandStart())
async def start(message: Message):
    init_db()
    await message.answer(
        "Привет! 👋\n\n"
        "Я помогу следить за расписанием и домашними заданиями.\n\n"
        "Главная фишка: добавляешь ДЗ с датой сдачи, а я сам покажу, "
        "что нужно сдать завтра.",
        reply_markup=menu()
    )


@dp.message(F.text == "➕ Добавить урок")
async def add_lesson_help(message: Message):
    await message.answer(
        "Отправь урок одной строкой:\n\n"
        "Понедельник | 1 | Математика\n"
        "Вторник | 3 | Физика\n\n"
        "Номер — пара по счёту."
    )


@dp.message(F.text == "📝 Добавить ДЗ")
async def add_hw_help(message: Message):
    await message.answer(
        "Отправь ДЗ одной строкой:\n\n"
        "Математика | Решить №1-10 | 2026-10-07\n\n"
        "Формат:\nПредмет | задание | дата сдачи\n\n"
        "Дата: ГГГГ-ММ-ДД"
    )


@dp.message(F.text == "📋 ДЗ на завтра")
async def homework_tomorrow(message: Message):
    tomorrow, _ = next_day()
    conn = db()
    rows = conn.execute(
        "SELECT id, subject, task FROM homework "
        "WHERE user_id=? AND due_date=? AND done=0 ORDER BY id",
        (message.from_user.id, tomorrow.isoformat())
    ).fetchall()
    conn.close()

    if not rows:
        await message.answer(
            f"🎉 На завтра ({tomorrow.strftime('%d.%m')}) "
            "невыполненного ДЗ нет."
        )
        return

    text = [f"📝 ДЗ на завтра — {tomorrow.strftime('%d.%m')}:\n"]
    for i, r in enumerate(rows, 1):
        text.append(f"{i}. {r['subject']}: {r['task']}  (ID {r['id']})")
    text.append("\nПосле выполнения нажми «✅ Выполнить ДЗ» и отправь ID.")
    await message.answer("\n".join(text))


@dp.message(F.text == "📅 Сегодня")
async def today(message: Message):
    d = datetime.now().date()
    wd = d.isoweekday()

    conn = db()
    lessons = conn.execute(
        "SELECT lesson_num, subject FROM schedule "
        "WHERE user_id=? AND weekday=? ORDER BY lesson_num",
        (message.from_user.id, wd)
    ).fetchall()
    hw = conn.execute(
        "SELECT subject, task FROM homework "
        "WHERE user_id=? AND due_date=? AND done=0",
        (message.from_user.id, d.isoformat())
    ).fetchall()
    conn.close()

    lines = [f"📅 Сегодня — {DAY_NAMES[wd]} ({d.strftime('%d.%m')})\n"]
    if lessons:
        lines.append("🎓 Пары:")
        for x in lessons:
            lines.append(f"{x['lesson_num']}. {x['subject']}")
    else:
        lines.append("🎓 Пары: расписание не добавлено.")

    if hw:
        lines.append("\n📝 Сдать сегодня:")
        for x in hw:
            lines.append(f"• {x['subject']}: {x['task']}")
    else:
        lines.append("\n📝 ДЗ на сегодня нет.")

    await message.answer("\n".join(lines))


@dp.message(F.text == "📚 Расписание")
async def schedule(message: Message):
    conn = db()
    rows = conn.execute(
        "SELECT weekday, lesson_num, subject FROM schedule "
        "WHERE user_id=? ORDER BY weekday, lesson_num",
        (message.from_user.id,)
    ).fetchall()
    conn.close()

    if not rows:
        await message.answer(
            "Расписание пока пустое.\n\n"
            "Добавь урок:\nПонедельник | 1 | Математика"
        )
        return

    result = []
    for wd in range(1, 8):
        day = [r for r in rows if r["weekday"] == wd]
        if day:
            result.append(f"📅 {DAY_NAMES[wd]}")
            result.extend(f"{r['lesson_num']}. {r['subject']}" for r in day)
            result.append("")
    await message.answer("\n".join(result))


@dp.message(F.text == "✅ Выполнить ДЗ")
async def done_help(message: Message):
    await message.answer(
        "Отправь ID выполненного задания.\n"
        "Например: 12\n\n"
        "Посмотреть ID можно в «📋 ДЗ на завтра»."
    )


@dp.message()
async def text_commands(message: Message):
    text = (message.text or "").strip()

    # Добавление урока
    parts = [p.strip() for p in text.split("|")]
    if len(parts) == 3 and parts[0].capitalize() in DAY_NAMES.values():
        day_name, num, subject = parts
        try:
            lesson_num = int(num)
            weekday = next(k for k, v in DAY_NAMES.items() if v.lower() == day_name.lower())
        except Exception:
            await message.answer("Не понял номер пары. Пример: Понедельник | 1 | Математика")
            return

        conn = db()
        conn.execute(
            "INSERT OR REPLACE INTO schedule(user_id, weekday, lesson_num, subject) "
            "VALUES (?, ?, ?, ?)",
            (message.from_user.id, weekday, lesson_num, subject)
        )
        conn.commit()
        conn.close()
        await message.answer(f"✅ Добавил: {day_name}, {lesson_num}-я пара — {subject}", reply_markup=menu())
        return

    # Добавление домашнего задания
    if len(parts) == 3:
        subject, task, due = parts
        try:
            datetime.strptime(due, "%Y-%m-%d")
        except ValueError:
            await message.answer("Дата должна быть в формате ГГГГ-ММ-ДД.")
            return

        conn = db()
        conn.execute(
            "INSERT INTO homework(user_id, subject, task, due_date) VALUES (?, ?, ?, ?)",
            (message.from_user.id, subject, task, due)
        )
        conn.commit()
        conn.close()
        await message.answer(
            f"✅ ДЗ добавлено.\n{subject}: {task}\nСдать: {due}",
            reply_markup=menu()
        )
        return

    # Отметка ДЗ выполненным по ID
    if text.isdigit():
        hw_id = int(text)
        conn = db()
        cur = conn.execute(
            "UPDATE homework SET done=1 WHERE id=? AND user_id=?",
            (hw_id, message.from_user.id)
        )
        conn.commit()
        conn.close()
        if cur.rowcount:
            await message.answer("✅ Отметил как выполненное.", reply_markup=menu())
        else:
            await message.answer("Не нашёл такое ДЗ у тебя.")
        return

    await message.answer(
        "Не понял команду.\n\n"
        "Добавить урок: Понедельник | 1 | Математика\n"
        "Добавить ДЗ: Математика | Решить №1-10 | 2026-10-07",
        reply_markup=menu()
    )


async def main():
    if not TOKEN or TOKEN == "8805517591:AAF0TqlI-SbGFu1RDEk89_OJ4isGVA__yKc":
        raise RuntimeError("Токен бота не найден!")
    init_db()
    bot = Bot(token=TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
