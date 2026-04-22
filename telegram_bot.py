"""
telegram_bot.py — центральная точка входа с debug-командами.
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
from debug_tool import debug_page, debug_test_page

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


# ─── Очередь callback'ов ──────────────────────────────────────

callback_queue = queue.Queue()


def wait_for_agent_callback(allowed: list, timeout: int = 600) -> str:
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


from telegram_notifier import TelegramNotifier
TelegramNotifier.wait_for_callback = lambda self, allowed, timeout=600: \
    wait_for_agent_callback(allowed, timeout)


# ─── Парсинг расписания ───────────────────────────────────────

def parse_schedule(text: str) -> list:
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

    # ── DEBUG команды ──
    if text.startswith("/debug_test "):
        url = text.replace("/debug_test ", "", 1).strip()
        if url:
            send("🧪 Запускаю отладку теста...")
            threading.Thread(target=lambda: debug_test_page(url), daemon=True).start()
        else:
            send("Укажи URL теста:\n<code>/debug_test https://campus.fa.ru/mod/quiz/view.php?id=...</code>")
        return

    if text.startswith("/debug "):
        url = text.replace("/debug ", "", 1).strip()
        if url:
            send("🔍 Запускаю отладку страницы...")
            threading.Thread(target=lambda: debug_page(url), daemon=True).start()
        else:
            send("Укажи URL:\n<code>/debug https://campus.fa.ru/...</code>")
        return

    # ── Основные команды ──
    if text == "/start":
        send(
            "👋 <b>Агент для заочного обучения</b>\n\n"
            "<b>Команды:</b>\n"
            "/scan — сканировать все курсы\n"
            "/subjects — список предметов\n"
            "/debug URL — что видит бот на странице (скрин + структура)\n"
            "/debug_test URL — отладка страницы теста\n"
            "/assignments — все задания\n"
            "/quizzes — все тесты\n"
            "/add — добавить предмет\n"
            "/help — помощь"
        )
        return

    if text == "/help":
        send(
            "<b>Обучение бота навигации:</b>\n\n"
            "1️⃣ <code>/debug URL</code> — бот заходит на страницу и шлёт:\n"
            "   • Скриншот что видит\n"
            "   • Заголовки и кнопки\n"
            "   • Все ссылки по категориям\n"
            "   • HTML главной области\n\n"
            "2️⃣ <code>/debug_test URL</code> — отладка теста:\n"
            "   • Скриншот теста\n"
            "   • HTML первого вопроса\n"
            "   • Структура вариантов ответов\n\n"
            "После того как увидишь структуру — перешли мне результаты, настрою селекторы."
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
        send("Формат: <code>Название|id|минуты</code>")
        return

    if text == "/scan":
        send("🔍 Запускаю сканирование...")
        threading.Thread(target=scan_all_courses, daemon=True).start()
        return

    if text == "/assignments":
        send("✍️ Запускаю все задания...")
        threading.Thread(target=run_all_assignments, daemon=True).start()
        return

    if text == "/quizzes":
        send("📝 Запускаю все тесты...")
        threading.Thread(target=run_all_quizzes, daemon=True).start()
        return

    # ── Добавление предмета ──
    if "|" in text and len(text.split("|")) == 3:
        name, sid, dur = [x.strip() for x in text.split("|")]
        try:
            registry.add(Subject(name=name, subject_id=sid, duration_minutes=int(dur)))
            send(f"✅ Добавлен: <b>{name}</b>")
        except ValueError:
            send("❌ Ошибка формата")
        return

    # ── Расписание ──
    if is_forward and re.search(r"\d{2}:\d{2}-\d{2}:\d{2}", text) and links:
        slots = parse_schedule(text)
        if not slots:
            send("Не смог разобрать расписание")
            return
        if not registry.all():
            send("⚠️ Предметов нет. Используй /scan")
            return
        pending[chat_id] = {"type": "schedule", "slots": slots, "links": links, "idx": 0}
        slot = slots[0]
        kb = subject_keyboard("sched")
        kb.append([{"text": "⏭ Пропустить", "callback_data": "sched_skip"}])
        send(
            f"📅 Нашёл {len(slots)} пар\n\n"
            f"<b>Пара 1:</b> {slot['start_time']} — {slot['title']}\n\n"
            f"Какой предмет?",
            keyboard=kb
        )
        return

    # ── Ссылки ──
    test_url = next(
        (l for l in links if "mts-link.ru" not in l and "webinar.ru" not in l),
        None
    )
    if not test_url and text.startswith("http") and "mts-link.ru" not in text:
        test_url = text

    if test_url:
        if not registry.all():
            send("⚠️ Предметов нет. Используй /scan")
            return
        is_quiz = "/mod/quiz/" in test_url
        ptype = "quiz" if is_quiz else "assignment"
        pending[chat_id] = {"type": ptype, "url": test_url}
        label = "тест" if is_quiz else "задание"
        send(f"🔗 Ссылка на {label}. Какой предмет?", keyboard=subject_keyboard(ptype))
        return

    webinar_url = next(
        (l for l in links if "mts-link.ru" in l or "webinar.ru" in l),
        None
    )
    if not webinar_url and ("mts-link.ru" in text or "webinar.ru" in text):
        webinar_url = text

    if webinar_url:
        if not registry.all():
            send("⚠️ Предметов нет. Используй /scan")
            return
        pending[chat_id] = {"type": "webinar", "url": webinar_url}
        send("🔗 Ссылка на эфир. Какой предмет?", keyboard=subject_keyboard("webinar"))
        return

    send("Не понял 🤔\n/help — помощь")


def handle_callback(data: str, callback_id: str, chat_id: str):
    answer_callback(callback_id)

    if data in ("approve", "skip"):
        callback_queue.put(data)
        return

    p = pending.get(chat_id)

    if data.startswith("sched:") and p and p["type"] == "schedule":
        subject = registry.get(data.split(":", 1)[1])
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
            target=lambda: SubjectAgent(subject).full_cycle(event_id=event_id, webinar_url=url),
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
            f"<b>Пара {p['idx'] + 1}:</b> {slot['start_time']} — {slot['title']}\n\n"
            f"Какой предмет?",
            keyboard=kb
        )
    else:
        pending.pop(chat_id, None)
        send("✅ Все пары запланированы!")


def main():
    print("🚀 Запуск Telegram бота...")
    required = ["TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID", "GROQ_API_KEY"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        print(f"❌ Не заданы переменные: {', '.join(missing)}")
        return

    send("🤖 Бот запущен!\nОтправь /start или /debug URL для отладки.")
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
