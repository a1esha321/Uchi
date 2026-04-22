"""
telegram_bot.py — центральная точка входа. Запускается на Railway.

Особенности:
- Единый polling Telegram API (избегаем конфликтов)
- Обработка callback'ов маршрутизируется в очереди для фоновых задач
- Парсинг расписания и планирование лекций
- Команды управления предметами
"""

import os
import re
import time
import threading
import queue
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv

from subjects import SubjectRegistry, Subject
from agent import SubjectAgent, scan_all_courses, run_all_assignments, run_all_quizzes

load_dotenv()


# ─── Telegram API ─────────────────────────────────────────────

def _token():
    t = os.getenv("TELEGRAM_TOKEN")
    if not t:
        raise ValueError("TELEGRAM_TOKEN не задан")
    return t


def _chat_id():
    c = os.getenv("TELEGRAM_CHAT_ID")
    if not c:
        raise ValueError("TELEGRAM_CHAT_ID не задан")
    return c


def _base():
    return f"https://api.telegram.org/bot{_token()}"


def send(text: str, keyboard=None) -> int:
    payload = {"chat_id": _chat_id(), "text": text[:4096], "parse_mode": "HTML"}
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": keyboard}
    try:
        r = requests.post(f"{_base()}/sendMessage", json=payload, timeout=15)
        data = r.json()
        if data.get("ok"):
            return data["result"]["message_id"]
        print(f"Telegram ошибка: {data}")
    except Exception as e:
        print(f"Telegram недоступен: {e}")
    return None


def answer_callback(callback_id: str):
    try:
        requests.post(
            f"{_base()}/answerCallbackQuery",
            json={"callback_query_id": callback_id},
            timeout=5
        )
    except Exception:
        pass


def get_updates(offset=None):
    params = {"timeout": 25}
    if offset:
        params["offset"] = offset
    try:
        r = requests.get(f"{_base()}/getUpdates", params=params, timeout=30)
        return r.json().get("result", [])
    except Exception as e:
        print(f"Ошибка polling: {e}")
        return []


# ─── Централизованная маршрутизация callback'ов ───────────────

# Очереди ожидания подтверждений от фоновых задач
# Агент: зовёт wait_callback(["approve", "skip"]) — блокируется
# Главный бот: получает callback_query — кладёт в эту очередь
callback_queue = queue.Queue()


def wait_for_agent_callback(allowed: list, timeout: int = 600) -> str:
    """Фоновая задача использует эту функцию для ожидания подтверждения."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        remaining = deadline - time.time()
        try:
            data = callback_queue.get(timeout=min(remaining, 10))
            if data in allowed:
                return data
        except queue.Empty:
            continue
    return None


# Подменяем метод wait_for_callback у TelegramNotifier,
# чтобы он работал через нашу центральную очередь
from telegram_notifier import TelegramNotifier
TelegramNotifier.wait_for_callback = lambda self, allowed, timeout=600: \
    wait_for_agent_callback(allowed, timeout)


# ─── Парсинг расписания ───────────────────────────────────────

def parse_schedule(text: str) -> list:
    """Извлекает из текста расписания все временные слоты."""
    slots = []
    pattern = r"(\d{2}:\d{2})-(\d{2}:\d{2})\.(.+?)(?=\d{2}:\d{2}-|\Z)"
    for start_time, end_time, block in re.findall(pattern, text, re.DOTALL):
        sh, sm = map(int, start_time.split(":"))
        eh, em = map(int, end_time.split(":"))
        duration = (eh * 60 + em) - (sh * 60 + sm)
        lines = [l.strip() for l in block.strip().split("\n") if l.strip()]
        title = re.sub(r"\(.*?\)", "", lines[-1]).strip() if lines else "Предмет"
        slots.append({
            "start_time": start_time,
            "duration": duration,
            "title": title
        })
    return slots


def extract_links(message: dict) -> list:
    """Извлекает URL из entities сообщения (синие ссылки)."""
    links = []
    text = message.get("text", "") or ""
    for entity in message.get("entities", []) or []:
        if entity.get("type") == "text_link":
            links.append(entity["url"])
        elif entity.get("type") == "url":
            links.append(text[entity["offset"]:entity["offset"] + entity["length"]])
    return links


# ─── Планировщик лекций ───────────────────────────────────────

def schedule_lecture(subject, start_time_str: str, duration: int,
                     event_id: str, webinar_url: str):
    """Ждёт нужное время и запускает лекцию."""

    def waiter():
        try:
            now = datetime.now()
            sh, sm = map(int, start_time_str.split(":"))
            target = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
            if target < now:
                target += timedelta(days=1)

            wait_sec = (target - now).total_seconds()
            mins = int(wait_sec / 60)

            send(f"⏰ <b>{subject.name}</b>\nСтарт в {start_time_str} (через {mins} мин)")
            time.sleep(wait_sec)

            subject.duration_minutes = duration
            SubjectAgent(subject).full_cycle(event_id=event_id, webinar_url=webinar_url)
        except Exception as e:
            send(f"❌ Ошибка планировщика [{subject.name}]: {e}")

    threading.Thread(target=waiter, daemon=True).start()


# ─── Обработка сообщений ──────────────────────────────────────

registry = SubjectRegistry()
pending = {}


def subject_keyboard(prefix: str) -> list:
    return [
        [{"text": s.name[:60], "callback_data": f"{prefix}:{s.subject_id}"}]
        for s in registry.all()
    ]


def handle_message(message: dict):
    text = (message.get("text") or "").strip()
    links = extract_links(message)
    is_forward = any(k in message for k in ("forward_date", "forward_from", "forward_origin"))
    chat_id = str(message["chat"]["id"])

    # ── Команды ──
    if text == "/start":
        send(
            "👋 <b>Агент для заочного обучения</b>\n\n"
            "<b>Что умею:</b>\n"
            "• Пересли расписание из Telegram — запланирую лекции\n"
            "• Отправь ссылку на тест — решу с подтверждением\n"
            "• Отправь ссылку на задание — выполню и покажу черновик\n\n"
            "<b>Команды:</b>\n"
            "/scan — просканировать все курсы на сайте\n"
            "/subjects — список предметов\n"
            "/assignments — выполнить все задания\n"
            "/quizzes — пройти все тесты\n"
            "/add — добавить предмет вручную\n"
            "/help — помощь"
        )
        return

    if text == "/help":
        send(
            "<b>Основные сценарии:</b>\n\n"
            "1️⃣ <b>Авто-сканирование</b>\n"
            "<code>/scan</code> — бот сам зайдёт на сайт, найдёт все курсы, тесты и задания. "
            "Предметы создадутся автоматически.\n\n"
            "2️⃣ <b>Лекции</b>\n"
            "Перешли боту сообщение с расписанием (с синими ссылками на семинары). "
            "Бот распарсит время и спросит какой предмет.\n\n"
            "3️⃣ <b>Тесты и задания</b>\n"
            "Отправь прямую ссылку на тест или задание. Бот спросит предмет, "
            "решит, и пришлёт на подтверждение с кнопками.\n\n"
            "4️⃣ <b>Пакетная обработка</b>\n"
            "<code>/assignments</code> — все задания сразу\n"
            "<code>/quizzes</code> — все тесты сразу"
        )
        return

    if text == "/subjects":
        subjects = registry.all()
        if not subjects:
            send("Предметов нет. Используй /scan или /add")
            return
        lines = ["<b>📚 Предметы:</b>\n"]
        for s in subjects:
            knowledge = s.get_full_knowledge()
            w = len(knowledge.split()) if knowledge else 0
            lines.append(
                f"<b>{s.name}</b>\n"
                f"  ID: <code>{s.subject_id}</code>\n"
                f"  Конспектов: {len(s.notes_files)} | Слов: {w}\n"
                f"  Тестов: {len(s.quiz_urls)} | Заданий: {len(s.assignment_urls)}\n"
            )
        send("\n".join(lines))
        return

    if text == "/add":
        send("Формат: <code>Название|id|минуты</code>\n"
             "Пример: <code>Коммуникации|comm|90</code>")
        return

    if text == "/scan":
        send("🔍 Запускаю сканирование...")
        threading.Thread(target=scan_all_courses, daemon=True).start()
        return

    if text == "/assignments":
        send("✍️ Запускаю все задания по всем предметам...")
        threading.Thread(target=run_all_assignments, daemon=True).start()
        return

    if text == "/quizzes":
        send("📝 Запускаю все тесты по всем предметам...")
        threading.Thread(target=run_all_quizzes, daemon=True).start()
        return

    # ── Добавление предмета ──
    if "|" in text and len(text.split("|")) == 3:
        name, sid, dur = [x.strip() for x in text.split("|")]
        try:
            registry.add(Subject(
                name=name, subject_id=sid,
                duration_minutes=int(dur)
            ))
            send(f"✅ Добавлен: <b>{name}</b>")
        except ValueError:
            send("❌ Ошибка формата. Пример: <code>Маркетинг|marketing|90</code>")
        return

    # ── Пересланное расписание ──
    if is_forward and re.search(r"\d{2}:\d{2}-\d{2}:\d{2}", text) and links:
        slots = parse_schedule(text)
        if not slots:
            send("Не смог разобрать расписание")
            return
        if not registry.all():
            send("⚠️ Предметов нет. Используй /scan или /add")
            return

        pending[chat_id] = {
            "type": "schedule",
            "slots": slots,
            "links": links,
            "idx": 0
        }
        slot = slots[0]
        kb = subject_keyboard("sched")
        kb.append([{"text": "⏭ Пропустить", "callback_data": "sched_skip"}])
        send(
            f"📅 Нашёл {len(slots)} пар\n\n"
            f"<b>Пара 1:</b> {slot['start_time']} — {slot['title']} ({slot['duration']} мин)\n\n"
            f"Какой предмет?",
            keyboard=kb
        )
        return

    # ── Ссылка на тест (домен университета, не МТС Линк) ──
    test_url = next(
        (l for l in links if "mts-link.ru" not in l and "webinar.ru" not in l),
        None
    )
    if not test_url and text.startswith("http") and "mts-link.ru" not in text:
        test_url = text

    if test_url:
        if not registry.all():
            send("⚠️ Предметов нет. Используй /scan или /add")
            return
        # Определяем — тест или задание по URL
        is_quiz = "/mod/quiz/" in test_url or "quiz" in test_url.lower()
        ptype = "quiz" if is_quiz else "assignment"
        pending[chat_id] = {"type": ptype, "url": test_url}
        label = "тест" if is_quiz else "задание"
        send(f"🔗 Ссылка на {label}. Какой предмет?", keyboard=subject_keyboard(ptype))
        return

    # ── Ссылка на эфир ──
    webinar_url = next(
        (l for l in links if "mts-link.ru" in l or "webinar.ru" in l),
        None
    )
    if not webinar_url and ("mts-link.ru" in text or "webinar.ru" in text):
        webinar_url = text

    if webinar_url:
        if not registry.all():
            send("⚠️ Предметов нет. Используй /scan или /add")
            return
        pending[chat_id] = {"type": "webinar", "url": webinar_url}
        send("🔗 Ссылка на эфир. Какой предмет?", keyboard=subject_keyboard("webinar"))
        return

    send("Не понял 🤔\n/start — помощь")


# ─── Callback routing ─────────────────────────────────────────

def handle_callback(data: str, callback_id: str, chat_id: str):
    answer_callback(callback_id)

    # Простые approve/skip — идут в очередь для фоновых задач
    if data in ("approve", "skip"):
        callback_queue.put(data)
        return

    p = pending.get(chat_id)

    # Расписание — выбор предмета
    if data.startswith("sched:") and p and p["type"] == "schedule":
        subject_id = data.split(":", 1)[1]
        subject = registry.get(subject_id)
        if not subject:
            send("❌ Предмет не найден")
            return
        idx = p["idx"]
        slot = p["slots"][idx]
        link = p["links"][idx] if idx < len(p["links"]) else p["links"][-1]
        event_id = link.rstrip("/").split("/")[-1]

        if event_id not in subject.event_ids:
            subject.event_ids.append(event_id)
            registry._save()

        schedule_lecture(subject, slot["start_time"], slot["duration"], event_id, link)
        _next_schedule_slot(p, chat_id)
        return

    if data == "sched_skip" and p and p["type"] == "schedule":
        _next_schedule_slot(p, chat_id)
        return

    # Тест — выбор предмета
    if data.startswith("quiz:") and p and p["type"] == "quiz":
        subject = registry.get(data.split(":", 1)[1])
        if not subject:
            send("❌ Предмет не найден")
            return
        url = p["url"]
        pending.pop(chat_id, None)
        send(f"🧠 Решаю тест: <b>{subject.name}</b>")
        threading.Thread(
            target=lambda: SubjectAgent(subject).run_quiz_by_url(url),
            daemon=True
        ).start()
        return

    # Задание — выбор предмета
    if data.startswith("assignment:") and p and p["type"] == "assignment":
        subject = registry.get(data.split(":", 1)[1])
        if not subject:
            send("❌ Предмет не найден")
            return
        url = p["url"]
        pending.pop(chat_id, None)
        send(f"✍️ Выполняю задание: <b>{subject.name}</b>")
        threading.Thread(
            target=lambda: SubjectAgent(subject).run_assignment_by_url(url),
            daemon=True
        ).start()
        return

    # Эфир — выбор предмета
    if data.startswith("webinar:") and p and p["type"] == "webinar":
        subject = registry.get(data.split(":", 1)[1])
        if not subject:
            send("❌ Предмет не найден")
            return
        url = p["url"]
        event_id = url.rstrip("/").split("/")[-1]
        if event_id not in subject.event_ids:
            subject.event_ids.append(event_id)
            registry._save()
        pending.pop(chat_id, None)
        send(f"🚀 Запускаю лекцию: <b>{subject.name}</b>")
        threading.Thread(
            target=lambda: SubjectAgent(subject).full_cycle(
                event_id=event_id, webinar_url=url
            ),
            daemon=True
        ).start()
        return


def _next_schedule_slot(p: dict, chat_id: str):
    p["idx"] += 1
    if p["idx"] < len(p["slots"]):
        slot = p["slots"][p["idx"]]
        kb = subject_keyboard("sched")
        kb.append([{"text": "⏭ Пропустить", "callback_data": "sched_skip"}])
        send(
            f"<b>Пара {p['idx'] + 1}:</b> {slot['start_time']} — "
            f"{slot['title']} ({slot['duration']} мин)\n\n"
            f"Какой предмет?",
            keyboard=kb
        )
    else:
        pending.pop(chat_id, None)
        send("✅ Все пары запланированы!")


# ─── Главный цикл ─────────────────────────────────────────────

def main():
    print("🚀 Запуск Telegram бота...")

    # Проверяем переменные окружения
    required = ["TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID", "GROQ_API_KEY"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        print(f"❌ Не заданы переменные: {', '.join(missing)}")
        return

    send("🤖 Бот запущен!\n\n"
         "Отправь /start для справки или /scan для сканирования сайта.")
    print("🤖 Бот ожидает сообщений...")

    my_chat = str(_chat_id())
    offset = None

    while True:
        try:
            updates = get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1

                msg = update.get("message")
                if msg:
                    chat_id = str(msg["chat"]["id"])
                    if chat_id == my_chat:
                        handle_message(msg)

                cb = update.get("callback_query")
                if cb:
                    chat_id = str(cb["message"]["chat"]["id"])
                    if chat_id == my_chat:
                        handle_callback(cb["data"], cb["id"], chat_id)
        except Exception as e:
            print(f"⚠️ Ошибка в основном цикле: {e}")
            time.sleep(5)

        time.sleep(0.5)


if __name__ == "__main__":
    main()
