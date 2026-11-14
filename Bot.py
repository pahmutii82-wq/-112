import asyncio
import sqlite3
import random
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

TOKEN = "9158588934:AAHmj3Ek50z5Ewhw_gNiXbPL73Wmldn8FWM"
STORAGE_CHAT_ID = -1004297755579  # ID твоего чата с фильмами

bot = Bot(TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# ---------- База данных ----------
db = sqlite3.connect("movies.db")
db.execute("""
CREATE TABLE IF NOT EXISTS movies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    year INTEGER,
    genres TEXT,
    file_id TEXT NOT NULL,
    UNIQUE(file_id)
)
""")
db.commit()


def add_movie(title, year, genres, file_id):
    try:
        db.execute(
            "INSERT INTO movies (title, year, genres, file_id) VALUES (?,?,?,?)",
            (title, year, genres.lower(), file_id),
        )
        db.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def get_genres():
    rows = db.execute("SELECT genres FROM movies").fetchall()
    result = set()
    for (g,) in rows:
        for part in (g or "").split(","):
            part = part.strip()
            if part:
                result.add(part)
    return sorted(result)


def get_years():
    rows = db.execute(
        "SELECT DISTINCT year FROM movies WHERE year IS NOT NULL ORDER BY year DESC"
    ).fetchall()
    return [r[0] for r in rows]


# ---------- Приём фильмов из хранилища ----------
@router.channel_post(F.chat.id == STORAGE_CHAT_ID, F.video | F.document)
@router.message(F.chat.id == STORAGE_CHAT_ID, F.video | F.document)
async def save_movie(message: Message):
    caption = message.caption or ""
    parts = [p.strip() for p in caption.split("|")]
    if len(parts) < 3 or not parts[1].isdigit():
        await message.reply(
            "Подпись должна быть такой: Название | Год | Жанр1, Жанр2"
        )
        return

    title, year, genres = parts[0], int(parts[1]), parts[2]
    media = message.video or message.document
    if add_movie(title, year, genres, media.file_id):
        await message.reply(f"Добавлено: {title} ({year})")
    else:
        await message.reply("Этот файл уже есть в базе.")


# ---------- Меню ----------
def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Случайный фильм", callback_data="random")],
        [InlineKeyboardButton(text="🎭 По жанру", callback_data="genres")],
        [InlineKeyboardButton(text="📅 По году", callback_data="years")],
    ])


@router.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "Привет! Выбери, что показать, или просто напиши название фильма.",
        reply_markup=main_menu(),
    )


async def send_movie(chat_id, row):
    _, title, year, genres, file_id = row
    await bot.send_video(
        chat_id, file_id, caption=f"{title} ({year})\n{genres}"
    )


@router.callback_query(F.data == "random")
async def random_movie(cb: CallbackQuery):
    rows = db.execute("SELECT * FROM movies").fetchall()
    if not rows:
        await cb.answer("База пока пуста", show_alert=True)
        return
    await send_movie(cb.message.chat.id, random.choice(rows))
    await cb.answer()


@router.callback_query(F.data == "genres")
async def show_genres(cb: CallbackQuery):
    genres = get_genres()
    if not genres:
        await cb.answer("Жанров пока нет", show_alert=True)
        return
    kb = [[InlineKeyboardButton(text=g.capitalize(), callback_data=f"g:{g}")]
          for g in genres]
    await cb.message.answer("Выбери жанр:",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await cb.answer()


@router.callback_query(F.data.startswith("g:"))
async def by_genre(cb: CallbackQuery):
    genre = cb.data[2:]
    rows = db.execute(
        "SELECT * FROM movies WHERE genres LIKE ?", (f"%{genre}%",)
    ).fetchall()
    if not rows:
        await cb.answer("Ничего не найдено", show_alert=True)
        return
    # показываем до 5 случайных из жанра
    for row in random.sample(rows, min(5, len(rows))):
        await send_movie(cb.message.chat.id, row)
    await cb.answer()


@router.callback_query(F.data == "years")
async def show_years(cb: CallbackQuery):
    years = get_years()
    if not years:
        await cb.answer("Годов пока нет", show_alert=True)
        return
    buttons = [InlineKeyboardButton(text=str(y), callback_data=f"y:{y}")
               for y in years]
    kb = [buttons[i:i + 4] for i in range(0, len(buttons), 4)]
    await cb.message.answer("Выбери год:",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await cb.answer()


@router.callback_query(F.data.startswith("y:"))
async def by_year(cb: CallbackQuery):
    year = int(cb.data[2:])
    rows = db.execute("SELECT * FROM movies WHERE year = ?", (year,)).fetchall()
    for row in rows[:5]:
        await send_movie(cb.message.chat.id, row)
    await cb.answer()


# ---------- Поиск по названию (любой текст) ----------
@router.message(F.text & ~F.text.startswith("/"))
async def search(message: Message):
    q = message.text.strip().lower()
    rows = db.execute("SELECT * FROM movies").fetchall()
    found = [r for r in rows if q in r[1].lower()]
    if not found:
        await message.answer("Ничего не нашёл. Попробуй другое название.")
        return
    for row in found[:5]:
        await send_movie(message.chat.id, row)


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
