"""
telegram_bot.py — Telegram бот для управления агентом.

Команды:
  /start       — приветствие
  /scan        — обход всех курсов и решение тестов
  /status      — текущий статус агента
  /notes       — список сохранённых конспектов
  /grades      — текущие оценки по предметам
  /help        — список команд

Отправь ссылку на эфир МТС Линк — бот запустит лекцию автоматически.
"""

import os
import threading
import asyncio
from datetime import datetime
from dotenv import load_dotenv

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_USER_ID = int(os.getenv("TELEGRAM_USER_ID", "0"))  # только ты можешь управлять

# Глобальный статус агента
agent_status = {
    "running": False,
    "current_task": "Ожидание",
    "last_update": None,
    "completed_today": [],
    "errors": []
}


# ─── ЗАЩИТА: только ты можешь управлять ────────────────────

def is_authorized(update: Update) -> bool:
    if ALLOWED_USER_ID == 0:
        return True  # если ID не задан — пускаем всех (только для теста!)
    return update.effective_user.id == ALLOWED_USER_ID


# ─── КЛАВИАТУРА ────────────────────────────────────────────

def get_keyboard():
    return ReplyKeyboardMarkup([
        ["🔍 Обход сайта", "📊 Статус"],
        ["📚 Конспекты", "🎓 Оценки"],
        ["❓ Помощь"]
    ], resize_keyboard=True)


# ─── КОМАНДЫ ───────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    await update.message.reply_text(
        "🎓 *Агент учёбы запущен!*\n\n"
        "Что умею:\n"
        "• Принимаю ссылки на эфиры МТС Линк → слушаю лекцию\n"
        "• Обхожу campus.fa.ru и решаю тесты\n"
        "• Присылаю отчёты о проделанной работе\n"
        "• Отвечаю на вопросы по расписанию\n\n"
        "Отправь ссылку на эфир или нажми кнопку ниже 👇",
        parse_mode="Markdown",
        reply_markup=get_keyboard()
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    await update.message.reply_text(
        "📋 *Команды:*\n\n"
        "🔍 *Обход сайта* — зайти на campus.fa.ru и решить все найденные тесты\n"
        "📊 *Статус* — что сейчас делает агент\n"
        "📚 *Конспекты* — список сохранённых конспектов лекций\n"
        "🎓 *Оценки* — текущие оценки по предметам\n\n"
        "📌 *Отправь ссылку:*\n"
        "• `https://events.mts-link.ru/...` — запустить лекцию\n"
        "• `https://campus.fa.ru/mod/quiz/...` — решить конкретный тест\n",
        parse_mode="Markdown",
        reply_markup=get_keyboard()
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    status = "🟢 Свободен" if not agent_status["running"] else "🔴 Работает"
    task = agent_status["current_task"]
    last = agent_status["last_update"]
    done = agent_status["completed_today"]

    text = f"*Статус агента:* {status}\n"
    text += f"*Задача:* {task}\n"
    if last:
        text += f"*Обновлено:* {last}\n"
    if done:
        text += f"\n✅ *Выполнено сегодня ({len(done)}):*\n"
        for item in done[-5:]:  # последние 5
            text += f"  • {item}\n"
    if agent_status["errors"]:
        text += f"\n⚠️ *Ошибки:* {len(agent_status['errors'])}\n"
        text += f"  Последняя: {agent_status['errors'][-1][:100]}\n"

    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    notes_dir = "notes"
    if not os.path.exists(notes_dir):
        await update.message.reply_text("📭 Конспектов пока нет. Отправь ссылку на лекцию!")
        return

    files = sorted(os.listdir(notes_dir), reverse=True)
    if not files:
        await update.message.reply_text("📭 Конспектов пока нет.")
        return

    text = f"📚 *Конспекты ({len(files)} шт):*\n\n"
    for f in files[:10]:
        size = os.path.getsize(os.path.join(notes_dir, f))
        words = size // 5  # приблизительно
        text += f"  📄 `{f}` (~{words} слов)\n"

    if len(files) > 10:
        text += f"\n  ...и ещё {len(files) - 10} файлов"

    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_grades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    # Реальные оценки из скриншотов — обновляй по мере изменений
    grades = {
        "Алгебра и анализ (1 сем)": 50.0,
        "Безопасность жизнедеятельности": 80.0,
        "Дискретная математика": 60.0,
        "Иностранный язык (1 сем)": 55.5,
        "История России": 68.2,
        "Практикум по программированию": 54.0,
        "Осн. рос. государственности": 0.0,
        "Физическая культура": 95.0,
        "История ФУ": 100.0,
    }

    text = "🎓 *Текущие оценки:*\n\n"
    for subject, grade in sorted(grades.items(), key=lambda x: x[1]):
        if grade == 0:
            emoji = "🔴"
        elif grade < 60:
            emoji = "⚠️"
        elif grade < 75:
            emoji = "🟡"
        else:
            emoji = "✅"
        text += f"{emoji} {subject}: *{grade}*\n"

    text += "\n_Оценки обновляются вручную в telegram\\_bot.py_"
    await update.message.reply_text(text, parse_mode="Markdown")


# ─── ОБХОД САЙТА ───────────────────────────────────────────

async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    if agent_status["running"]:
        await update.message.reply_text("⏳ Агент уже работает: " + agent_status["current_task"])
        return

    await update.message.reply_text(
        "🔍 Запускаю обход campus.fa.ru...\n"
        "Найду все тесты и решу их. Отчёт пришлю после!"
    )

    # Запускаем в отдельном потоке чтобы не блокировать бота
    thread = threading.Thread(
        target=_run_scan_sync,
        args=(update.effective_chat.id, context.application),
        daemon=True
    )
    thread.start()


def _run_scan_sync(chat_id: int, app):
    """Синхронный обход — запускается в отдельном потоке"""
    from navigator import Navigator

    agent_status["running"] = True
    agent_status["current_task"] = "Обход campus.fa.ru"
    agent_status["last_update"] = datetime.now().strftime("%H:%M:%S")

    results = []
    errors = []

    try:
        nav = Navigator(headless=True)

        # Патчим методы навигатора для отправки прогресса в Telegram
        original_solve = nav._solve_quiz

        def patched_solve(url, knowledge):
            original_solve(url, knowledge)
            name = url.split("id=")[-1]
            results.append(f"Тест #{name}")
            agent_status["completed_today"].append(f"Тест #{name}")
            agent_status["last_update"] = datetime.now().strftime("%H:%M:%S")
            # Уведомление о каждом тесте
            asyncio.run(_send_message(app, chat_id, f"✅ Сдан тест: {url[-30:]}"))

        nav._solve_quiz = patched_solve
        nav.run_full_scan()

    except Exception as e:
        errors.append(str(e))
        agent_status["errors"].append(str(e))
        asyncio.run(_send_message(app, chat_id, f"❌ Ошибка при обходе: {e}"))
    finally:
        agent_status["running"] = False
        agent_status["current_task"] = "Ожидание"

    # Итоговый отчёт
    report = f"📊 *Обход завершён!*\n\n"
    report += f"✅ Решено тестов: {len(results)}\n"
    if results:
        report += "\n".join([f"  • {r}" for r in results])
    if errors:
        report += f"\n⚠️ Ошибок: {len(errors)}"

    asyncio.run(_send_message(app, chat_id, report))


# ─── ОБРАБОТКА ССЫЛОК ──────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    text = update.message.text.strip()

    # Кнопки клавиатуры
    if "Обход сайта" in text:
        await cmd_scan(update, context)
        return
    if "Статус" in text:
        await cmd_status(update, context)
        return
    if "Конспекты" in text:
        await cmd_notes(update, context)
        return
    if "Оценки" in text:
        await cmd_grades(update, context)
        return
    if "Помощь" in text:
        await cmd_help(update, context)
        return

    # Ссылка на эфир МТС Линк
    if "mts-link.ru" in text or "webinar.ru" in text or "events.mts-link" in text:
        await _handle_lecture_link(update, context, text)
        return

    # Ссылка на конкретный тест
    if "campus.fa.ru/mod/quiz" in text:
        await _handle_quiz_link(update, context, text)
        return

    # Вопрос агенту (Claude отвечает)
    await _handle_question(update, context, text)


async def _handle_lecture_link(update, context, url: str):
    """Запускает прослушивание лекции по ссылке"""
    if agent_status["running"]:
        await update.message.reply_text("⏳ Агент занят: " + agent_status["current_task"])
        return

    # Извлекаем event_id из URL
    event_id = url.rstrip("/").split("/")[-1]

    await update.message.reply_text(
        f"🎓 Запускаю лекцию!\n"
        f"ID эфира: `{event_id}`\n\n"
        f"Буду слушать и составлять конспект. "
        f"Пришлю итоги когда закончится 📝",
        parse_mode="Markdown"
    )

    thread = threading.Thread(
        target=_run_lecture_sync,
        args=(update.effective_chat.id, context.application, url, event_id),
        daemon=True
    )
    thread.start()


def _run_lecture_sync(chat_id: int, app, webinar_url: str, event_id: str):
    """Слушает лекцию в отдельном потоке"""
    from lecture_listener import LectureListener
    from presence import PresenceKeeper

    agent_status["running"] = True
    agent_status["current_task"] = f"Лекция {event_id}"
    agent_status["last_update"] = datetime.now().strftime("%H:%M:%S")

    try:
        presence = PresenceKeeper(webinar_url)
        presence.start()

        listener = LectureListener(event_id)
        knowledge = listener.listen_realtime(90)
        presence.stop()

        notes_file = listener.save_notes()
        words = len(knowledge.split())

        agent_status["completed_today"].append(f"Лекция {event_id}")

        # Краткое резюме
        from smart_solver import SmartSolver
        if knowledge.strip():
            solver = SmartSolver(knowledge)
            summary = solver.make_summary()
        else:
            summary = "Субтитры недоступны — конспект пуст."

        report = (
            f"✅ *Лекция завершена!*\n\n"
            f"📄 Конспект: `{notes_file}`\n"
            f"📝 Слов записано: {words}\n\n"
            f"*Краткое резюме:*\n{summary}"
        )
        asyncio.run(_send_message(app, chat_id, report))

    except Exception as e:
        agent_status["errors"].append(str(e))
        asyncio.run(_send_message(app, chat_id, f"❌ Ошибка лекции: {e}"))
    finally:
        agent_status["running"] = False
        agent_status["current_task"] = "Ожидание"


async def _handle_quiz_link(update, context, url: str):
    """Решает конкретный тест по ссылке"""
    await update.message.reply_text(f"🧪 Решаю тест...\n`{url}`", parse_mode="Markdown")

    thread = threading.Thread(
        target=_run_quiz_sync,
        args=(update.effective_chat.id, context.application, url),
        daemon=True
    )
    thread.start()


def _run_quiz_sync(chat_id: int, app, quiz_url: str):
    from navigator import Navigator
    try:
        nav = Navigator(headless=True)
        nav.bot.login()
        nav._solve_quiz(quiz_url, "")
        asyncio.run(_send_message(app, chat_id, f"✅ Тест сдан!\n`{quiz_url}`"))
    except Exception as e:
        asyncio.run(_send_message(app, chat_id, f"❌ Ошибка теста: {e}"))


async def _handle_question(update, context, question: str):
    """Claude отвечает на организационные вопросы"""
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    await update.message.reply_text("🤔 Думаю...")

    try:
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            system=(
                "Ты помощник студента Финансового университета (campus.fa.ru). "
                "Отвечай кратко и по делу на вопросы об учёбе, расписании, заданиях. "
                "Если вопрос не об учёбе — вежливо скажи что не знаешь."
            ),
            messages=[{"role": "user", "content": question}]
        )
        answer = msg.content[0].text
        await update.message.reply_text(answer)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


# ─── ВСПОМОГАТЕЛЬНЫЕ ──────────────────────────────────────

async def _send_message(app, chat_id: int, text: str):
    """Отправляет сообщение из синхронного потока"""
    try:
        await app.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Ошибка отправки: {e}")


# ─── ЗАПУСК ───────────────────────────────────────────────

def main():
    if not TELEGRAM_TOKEN:
        print("❌ Добавь TELEGRAM_TOKEN в .env файл!")
        return

    print("🤖 Telegram бот запускается...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("notes", cmd_notes))
    app.add_handler(CommandHandler("grades", cmd_grades))
    app.add_handler(CommandHandler("scan", cmd_scan))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ Бот запущен! Открой Telegram и напиши /start")
    app.run_polling()


if __name__ == "__main__":
    main()
