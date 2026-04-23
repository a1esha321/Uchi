"""
telegram_bot.py — главная точка входа.

Команды:
  /start          — помощь
  /scan           — сканировать campus.fa.ru (семестр из SEMESTER env)
  /scan_online    — сканировать online.fa.ru
  /subjects       — список предметов (с флагами)
  /course <id>    — карточка конкретного курса
  /upcoming       — дедлайны из календаря Moodle
  /reminders      — предстоящие дедлайны с таймером
  /quizzes        — пройти все тесты (с подтверждением)
  /assignments    — выполнить все задания (с подтверждением)
  /preview <url>  — dry-run теста/задания (решить но не отправлять)
  /learn          — микро-квиз по теме с низкой уверенностью
  /map            — карта знаний: слабые и сильные темы
  /stats          — статистика работы бота
  /cache          — статистика кэша Q&A
  /export <id>    — экспорт конспектов предмета
  /teachers       — список преподавателей
  /debug <url>    — отладка страницы
  /debug_test <url> — отладка теста
  /debug_course <url> — дамп курса для анализа селекторов
  /add Имя|id|минуты — добавить предмет вручную
"""

import os
import re
import random
import time
import threading
import queue
import json
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv

from subjects import SubjectRegistry, Subject, TeacherRegistry, Stats
from agent import (
    SubjectAgent, scan_all_courses, scan_online_fa_courses,
    run_all_assignments, run_all_quizzes,
    get_upcoming_deadlines, ONLINE_FA_URL,
)
from debug_tool import debug_page, debug_test_page
from qa_cache import QACache
from reactor_core import KnowledgeMirror

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
    except Exception as e:
        print(f"Telegram: {e}")
    return None


def send_document(file_path: str, caption: str = "") -> bool:
    try:
        with open(file_path, "rb") as f:
            r = requests.post(
                f"{_base()}/sendDocument",
                data={"chat_id": _chat_id(), "caption": caption[:1024], "parse_mode": "HTML"},
                files={"document": f},
                timeout=60
            )
            return r.json().get("ok", False)
    except Exception as e:
        print(f"Document: {e}")
        return False


def answer_callback(cb_id: str):
    try:
        requests.post(f"{_base()}/answerCallbackQuery",
                      json={"callback_query_id": cb_id}, timeout=5)
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
        print(f"Polling: {e}")
        return []


# ─── Централизованная очередь callback'ов ────────────────────

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


# ─── Парсинг расписания из Telegram ──────────────────────────

def parse_schedule(text: str) -> list:
    slots = []
    pattern = r"(\d{2}:\d{2})-(\d{2}:\d{2})\.(.+?)(?=\d{2}:\d{2}-|\Z)"
    for st, et, block in re.findall(pattern, text, re.DOTALL):
        sh, sm = map(int, st.split(":"))
        eh, em = map(int, et.split(":"))
        duration = (eh * 60 + em) - (sh * 60 + sm)
        lines = [l.strip() for l in block.strip().split("\n") if l.strip()]
        title = re.sub(r"\(.*?\)", "", lines[-1]).strip() if lines else "Предмет"
        slots.append({"start_time": st, "duration": duration, "title": title})
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


def schedule_lecture(subject, start_time: str, duration: int, event_id: str, webinar_url: str):
    def waiter():
        try:
            now = datetime.now()
            sh, sm = map(int, start_time.split(":"))
            target = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
            if target < now:
                target += timedelta(days=1)
            wait = (target - now).total_seconds()
            send(f"⏰ <b>{subject.name}</b> — старт в {start_time} (через {int(wait/60)} мин)")
            time.sleep(wait)
            subject.duration_minutes = duration
            SubjectAgent(subject).full_cycle(event_id=event_id, webinar_url=webinar_url)
        except Exception as e:
            send(f"❌ Ошибка [{subject.name}]: {e}")
    threading.Thread(target=waiter, daemon=True).start()


# ─── Парсинг дедлайнов ───────────────────────────────────────

_MONTH_MAP = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}


def _parse_deadline(s: str):
    """Парсит дедлайн из ISO или русского формата Moodle."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        pass
    # "1 мая 2024, 23:59" или "13 апреля 2024, 09:00"
    m = re.match(r"(\d{1,2})\s+(\w+)\s+(\d{4})[,\s]+(\d{1,2}):(\d{2})", s)
    if m:
        day, month_str, year, hour, minute = m.groups()
        month = _MONTH_MAP.get(month_str.lower())
        if month:
            try:
                return datetime(int(year), month, int(day), int(hour), int(minute))
            except Exception:
                pass
    return None


# ─── Напоминания о дедлайнах ─────────────────────────────────

REMINDERS_FILE = "reminders_sent.json"


def _load_reminders_sent() -> set:
    if os.path.exists(REMINDERS_FILE):
        try:
            with open(REMINDERS_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def _save_reminders_sent(sent: set):
    with open(REMINDERS_FILE, "w") as f:
        json.dump(list(sent), f)


def _deadline_reminder_loop():
    """Фоновый поток: каждые 30 минут проверяет дедлайны и шлёт напоминания."""
    while True:
        try:
            sent = _load_reminders_sent()
            now = datetime.now()
            reg = SubjectRegistry()

            for subject in reg.all():
                for url, deadline_str in subject.assignment_deadlines.items():
                    deadline = _parse_deadline(deadline_str)
                    if not deadline:
                        continue
                    delta = deadline - now
                    hours_left = delta.total_seconds() / 3600
                    if hours_left < 0:
                        continue
                    status = subject.assignment_status.get(url, "new")
                    if status in ("submitted", "graded"):
                        continue
                    for threshold_h, label in [(24, "24 часа"), (1, "1 час")]:
                        key = f"{url}_{threshold_h}h"
                        if hours_left <= threshold_h and key not in sent:
                            send(
                                f"⏰ <b>Дедлайн через {label}!</b>\n\n"
                                f"Предмет: <b>{subject.name}</b>\n"
                                f"Срок: {deadline.strftime('%d.%m.%Y %H:%M')}\n"
                                f"Задание: <code>{url[-60:]}</code>"
                            )
                            sent.add(key)

            _save_reminders_sent(sent)
        except Exception as e:
            print(f"⚠️ Reminder loop: {e}")
        time.sleep(1800)


# ─── Обработка сообщений ──────────────────────────────────────

registry = SubjectRegistry()
pending = {}

try:
    km = KnowledgeMirror()
except RuntimeError as _km_err:
    km = None
    print(f"⚠️ KnowledgeMirror не инициализирован: {_km_err}")

# chat_id → {'subject_id', 'topic', 'correct_answer', 'start_time'}
quiz_states: dict = {}


def _run_with_error_notify(fn):
    """Запускает fn(), при исключении шлёт ошибку в Telegram."""
    try:
        fn()
    except Exception as e:
        send(f"❌ Ошибка: {e}")


def refresh_registry():
    """Перечитывает реестр с диска (важно после /scan в фоновом потоке)."""
    global registry
    registry = SubjectRegistry()


def subject_keyboard(prefix: str, active_only: bool = True) -> list:
    refresh_registry()
    return [
        [{"text": s.name[:60], "callback_data": f"{prefix}:{s.subject_id}"}]
        for s in registry.all(active_only=active_only)
    ]


def handle_message(message: dict):
    text = (message.get("text") or "").strip()
    links = extract_links(message)
    is_forward = any(k in message for k in ("forward_date", "forward_from", "forward_origin"))
    chat_id = str(message["chat"]["id"])

    # ── Ответ на микро-квиз (/learn) ──
    if chat_id in quiz_states and not text.startswith("/"):
        state = quiz_states.pop(chat_id)
        if not km:
            send("⚠️ KnowledgeMirror недоступен — проверь GROQ_API_KEY")
            return

        def _eval():
            try:
                is_correct = km.evaluate_user_answer(text, state["correct_answer"])
                km.update_confidence(state["subject_id"], state["topic"], is_correct)
                km.log_session(
                    state["subject_id"], state["topic"],
                    state["start_time"], datetime.now(), is_correct,
                )
                if is_correct:
                    send("✅ Верно! Уверенность по теме повышена.")
                else:
                    send(
                        f"❌ Не совсем.\n\n"
                        f"<b>Эталон:</b> <i>{state['correct_answer'][:400]}</i>"
                    )
            except Exception as e:
                send(f"⚠️ Ошибка при проверке ответа: {e}")

        threading.Thread(target=_eval, daemon=True).start()
        return

    # ── Debug ──
    if text.startswith("/debug_course"):
        url = text[len("/debug_course"):].strip()
        if not url:
            send(
                "Использование: <code>/debug_course &lt;ссылка&gt;</code>\n"
                "Пример: <code>/debug_course https://online.fa.ru/course/view.php?id=12345</code>"
            )
            return
        if not url.startswith("http"):
            send("⚠️ Нужна полная ссылка, начиная с https://")
            return

        send("🔍 Открываю страницу и собираю дамп...")

        def _dump():
            import json as _json
            base = "https://online.fa.ru" if "online.fa.ru" in url else None
            bot_browser = UniBrowser(headless=True, base_url=base)
            try:
                bot_browser.login()
                report = bot_browser.debug_dump_page(url)
            finally:
                bot_browser.close()

            path = f"/tmp/debug_report_{int(time.time())}.json"
            with open(path, "w", encoding="utf-8") as f:
                _json.dump(report, f, ensure_ascii=False, indent=2)

            summary = (
                f"✅ <b>Дамп готов</b>\n\n"
                f"📄 Title: {report['title'][:100]}\n"
                f"🔗 Final URL: {report['final_url'][:120]}\n"
                f"H1: {len(report['h1_texts'])} | H2: {len(report['h2_texts'])}\n"
                f"Ссылок: {len(report['all_links'])}\n"
                f"Кнопок: {len(report['buttons'])}\n"
                f"iframes: {len(report['iframes'])}\n"
                f"🎯 Кандидатов в активности: {len(report['candidate_activities'])}"
            )
            send(summary)
            send_document(path, "📦 Полный дамп страницы (JSON)")

        threading.Thread(
            target=lambda: _run_with_error_notify(_dump),
            daemon=True
        ).start()
        return

    if text.startswith("/debug_test "):
        url = text[12:].strip()
        if url:
            send("🧪 Отладка теста...")
            threading.Thread(target=lambda: debug_test_page(url), daemon=True).start()
        return

    if text.startswith("/debug "):
        url = text[7:].strip()
        if url:
            send("🔍 Отладка страницы...")
            threading.Thread(target=lambda: debug_page(url), daemon=True).start()
        return

    # ── Preview (dry-run) ──
    if text.startswith("/preview "):
        url = text[9:].strip()
        if not url:
            send("Укажи URL: <code>/preview https://...</code>")
            return
        if not registry.all(active_only=True):
            send("⚠️ Предметов нет. Сначала /scan")
            return
        pending[chat_id] = {"type": "preview", "url": url}
        send("🔍 Dry-run. Какой предмет?", keyboard=subject_keyboard("preview"))
        return

    # ── Команды ──
    if text == "/start":
        send(
            "👋 <b>Агент для заочного обучения</b>\n\n"
            "<b>Основные:</b>\n"
            "/scan — просканировать campus.fa.ru\n"
            "/scan_online — просканировать online.fa.ru\n"
            "/subjects — список предметов\n"
            "/course <i>id</i> — карточка курса\n"
            "/upcoming — дедлайны из календаря\n"
            "/reminders — мои дедлайны (с таймером)\n"
            "/quizzes — пройти все тесты\n"
            "/assignments — все задания\n\n"
            "<b>Знания:</b>\n"
            "/learn — микро-квиз по слабой теме\n"
            "/map — карта знаний (сильные/слабые темы)\n\n"
            "<b>Дополнительно:</b>\n"
            "/preview <i>url</i> — dry-run\n"
            "/stats — статистика\n"
            "/cache — статистика кэша Q&A\n"
            "/export <i>id</i> — конспекты\n"
            "/teachers — преподаватели\n"
            "/debug <i>url</i> — отладка страницы\n"
            "/debug_course <i>url</i> — дамп курса (JSON)\n"
            "/help — подробнее"
        )
        return

    if text == "/help":
        send(
            "<b>Как работает:</b>\n\n"
            "1. <code>/scan</code> — бот находит все твои курсы, "
            "отделяет активные (текущий семестр) от сданных, помечает внешние платформы.\n\n"
            "2. Пересылаешь <b>расписание</b> → бот планирует лекции.\n\n"
            "3. Отправляешь <b>ссылку на тест</b> → бот решает с подтверждением.\n"
            "   — Если тест с 1 попыткой → отдельное подтверждение перед стартом.\n\n"
            "4. <code>/preview URL</code> — dry-run: решит, но НЕ отправит.\n\n"
            "5. <code>/upcoming</code> — что сдавать в ближайшее время.\n\n"
            "6. <code>/course subject_id</code> — карточка предмета со всеми деталями.\n\n"
            "Семестр задаётся переменной <code>SEMESTER</code> в Railway (по умолчанию 2)."
        )
        return

    if text == "/subjects":
        refresh_registry()
        subjects = registry.all()
        if not subjects:
            send("Предметов нет. Используй /scan")
            return
        lines = ["<b>📚 Все предметы:</b>\n"]
        for s in subjects:
            flags = []
            if s.completed:
                flags.append("✅ сдано")
            if s.source_platform == ONLINE_FA_URL:
                flags.append("🌐 online.fa.ru")
            elif s.external_platform:
                flags.append("🔗 внешний")
            if s.needs_enrollment:
                flags.append("📝 нужна запись")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            lines.append(
                f"<b>{s.name}</b>{flag_str}\n"
                f"  ID: <code>{s.subject_id}</code> | Сем: {s.semester or '?'}\n"
                f"  Тестов: {len(s.quiz_urls)} | Заданий: {len(s.assignment_urls)}\n"
            )
        send("\n".join(lines))
        return

    if text.startswith("/course "):
        refresh_registry()
        subject_id = text[8:].strip()
        subject = registry.get(subject_id)
        if not subject:
            send(f"Не нашёл предмет с ID <code>{subject_id}</code>")
            return

        flags = []
        if subject.completed: flags.append("✅ Сдано")
        if subject.source_platform == ONLINE_FA_URL: flags.append("🌐 online.fa.ru")
        elif subject.external_platform: flags.append("🔗 Внешняя платформа")
        if subject.needs_enrollment: flags.append("📝 Нужна запись")

        knowledge = subject.get_full_knowledge()
        words = len(knowledge.split()) if knowledge else 0

        quizzes_done = sum(1 for s in subject.quiz_status.values() if s == "done")
        assignments_done = sum(1 for s in subject.assignment_status.values() if s in ("submitted", "graded"))

        text_out = (
            f"<b>📚 {subject.name}</b>\n\n"
            f"ID: <code>{subject.subject_id}</code>\n"
            f"Семестр: {subject.semester or '?'}\n"
        )
        if flags:
            text_out += f"Флаги: {', '.join(flags)}\n"
        if subject.teacher_name:
            text_out += f"Преподаватель: <b>{subject.teacher_name}</b>\n"
        if subject.teacher_email:
            text_out += f"Email: <code>{subject.teacher_email}</code>\n"
        text_out += (
            f"\n<b>Активности:</b>\n"
            f"Тестов: {len(subject.quiz_urls)} (сдано: {quizzes_done})\n"
            f"Заданий: {len(subject.assignment_urls)} (сдано: {assignments_done})\n"
            f"Конспектов: {len(subject.notes_files)} ({words} слов)\n"
        )
        if subject.teacher_requirements:
            req_preview = subject.teacher_requirements[:400]
            text_out += f"\n<b>Требования:</b>\n<pre>{req_preview}</pre>"

        send(text_out)
        return

    if text == "/scan":
        current_semester = os.getenv("SEMESTER", "2")
        send(f"🔍 Сканирую campus.fa.ru (семестр: {current_semester})...")
        threading.Thread(
            target=lambda: scan_all_courses(current_semester=current_semester),
            daemon=True
        ).start()
        return

    if text == "/scan_online":
        send("🌐 Сканирую online.fa.ru...")
        threading.Thread(target=scan_online_fa_courses, daemon=True).start()
        return

    if text == "/upcoming":
        send("📅 Получаю дедлайны из календаря...")
        def _get():
            try:
                items = get_upcoming_deadlines()
                if not items:
                    send("Нет предстоящих событий")
                    return
                lines = ["<b>📅 Предстоящие дедлайны:</b>\n"]
                for item in items[:20]:
                    t = item["text"][:200].replace("\n", " · ")
                    lines.append(f"• {t}")
                send("\n".join(lines))
            except Exception as e:
                send(f"❌ Ошибка: {e}")
        threading.Thread(target=_get, daemon=True).start()
        return

    if text == "/stats":
        stats = Stats()
        send(stats.summary())
        return

    if text.startswith("/export "):
        subject_id = text[8:].strip()
        subject = registry.get(subject_id)
        if not subject:
            send(f"Не нашёл <code>{subject_id}</code>")
            return
        knowledge = subject.get_full_knowledge()
        if not knowledge:
            send(f"У <b>{subject.name}</b> пока нет конспектов")
            return
        path = f"/tmp/notes_{subject_id}.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"Предмет: {subject.name}\n")
            if subject.teacher_name:
                f.write(f"Преподаватель: {subject.teacher_name}\n")
            f.write(f"Дата экспорта: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n")
            f.write("=" * 50 + "\n\n")
            f.write(knowledge)
        send_document(path, f"📄 Конспекты: <b>{subject.name}</b>")
        return

    if text == "/teachers":
        teachers = TeacherRegistry().all()
        if not teachers:
            send("Преподаватели пока не собраны. Запусти /scan")
            return
        lines = ["<b>👨‍🏫 Преподаватели:</b>\n"]
        for key, t in list(teachers.items())[:20]:
            lines.append(f"<b>{t['name']}</b>")
            if t.get("email"):
                lines.append(f"  📧 <code>{t['email']}</code>")
            if t.get("courses"):
                courses_list = ", ".join(t['courses'][:3])
                lines.append(f"  📚 {courses_list}")
            lines.append("")
        send("\n".join(lines))
        return

    if text == "/assignments":
        send("✍️ Все задания (с подтверждением)...")
        threading.Thread(target=lambda: run_all_assignments(dry_run=False), daemon=True).start()
        return

    if text == "/quizzes":
        send("📝 Все тесты (с подтверждением)...")
        threading.Thread(target=lambda: run_all_quizzes(dry_run=False), daemon=True).start()
        return

    if text == "/add":
        send("Формат: <code>Название|id|минуты</code>")
        return

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
        if not slots or not registry.all(active_only=True):
            send("⚠️ Расписание не разобрано или нет активных предметов")
            return
        pending[chat_id] = {"type": "schedule", "slots": slots, "links": links, "idx": 0}
        slot = slots[0]
        kb = subject_keyboard("sched")
        kb.append([{"text": "⏭ Пропустить", "callback_data": "sched_skip"}])
        send(f"📅 {len(slots)} пар\n\n<b>Пара 1:</b> {slot['start_time']} — {slot['title']}",
             keyboard=kb)
        return

    # ── Ссылки ──
    uni_link = next((l for l in links if "mts-link.ru" not in l and "webinar.ru" not in l), None)
    if not uni_link and text.startswith("http") and "mts-link.ru" not in text:
        uni_link = text

    if uni_link:
        if not registry.all(active_only=True):
            send("⚠️ Нет активных предметов. Сначала /scan")
            return
        is_quiz = "/mod/quiz/" in uni_link
        ptype = "quiz" if is_quiz else "assignment"
        pending[chat_id] = {"type": ptype, "url": uni_link}
        label = "тест" if is_quiz else "задание"
        send(f"🔗 Ссылка на {label}. Какой предмет?",
             keyboard=subject_keyboard(ptype))
        return

    webinar_url = next((l for l in links if "mts-link.ru" in l or "webinar.ru" in l), None)
    if not webinar_url and ("mts-link.ru" in text or "webinar.ru" in text):
        webinar_url = text

    if webinar_url:
        if not registry.all(active_only=True):
            send("⚠️ Нет активных предметов")
            return
        pending[chat_id] = {"type": "webinar", "url": webinar_url}
        send("🔗 Ссылка на эфир. Какой предмет?",
             keyboard=subject_keyboard("webinar"))
        return

    if text == "/learn":
        if not km:
            send("⚠️ KnowledgeMirror недоступен — проверь GROQ_API_KEY")
            return
        refresh_registry()
        weak = km.get_weak_topics()

        if weak:
            subject_id, topic, conf = random.choice(weak)
            subject = registry.get(subject_id)
            subject_name = subject.name if subject else subject_id
        else:
            subjects_with_notes = [s for s in registry.all() if s.notes_files]
            if not subjects_with_notes:
                send("🎓 Пока нет конспектов для квиза. Посети хотя бы одну лекцию.")
                return
            subject = random.choice(subjects_with_notes)
            subject_id = subject.subject_id
            subject_name = subject.name
            topic = subject.name

        subject_obj = registry.get(subject_id)
        context = subject_obj.get_context_for_topic(topic) if subject_obj else ""
        if not context:
            send(f"⚠️ По предмету «{subject_name}» пока нет конспектов.")
            return

        send(f"🧠 Генерирую вопрос по теме <b>{topic}</b>...")

        def _generate():
            question, answer = km.generate_micro_quiz(subject_name, topic, context)
            if not answer:
                send("⚠️ Не удалось сгенерировать вопрос, попробуй ещё раз.")
                return
            quiz_states[chat_id] = {
                "subject_id": subject_id,
                "topic": topic,
                "correct_answer": answer,
                "start_time": datetime.now(),
            }
            send(
                f"🎓 <b>{subject_name}</b>\n\n"
                f"{question}\n\n"
                f"<i>Ответь следующим сообщением.</i>"
            )

        threading.Thread(target=_generate, daemon=True).start()
        return

    if text == "/map":
        if not km:
            send("⚠️ KnowledgeMirror недоступен — проверь GROQ_API_KEY")
            return
        send(km.get_knowledge_summary())
        return

    if text == "/reminders":
        refresh_registry()
        now = datetime.now()
        items = []
        for subject in registry.all():
            for url, deadline_str in subject.assignment_deadlines.items():
                deadline = _parse_deadline(deadline_str)
                if not deadline or deadline <= now:
                    continue
                status = subject.assignment_status.get(url, "new")
                delta = deadline - now
                items.append((deadline, subject.name, status, delta, url))
        items.sort(key=lambda x: x[0])
        if not items:
            send("Нет предстоящих дедлайнов")
            return
        lines = ["<b>⏰ Предстоящие дедлайны:</b>\n"]
        for deadline, name, status, delta, url in items[:15]:
            icon = "✅" if status in ("submitted", "graded") else "❗"
            days = delta.days
            hours = delta.seconds // 3600
            time_str = f"{days}д {hours}ч" if days > 0 else f"{hours}ч"
            lines.append(f"{icon} <b>{name}</b> — через {time_str} ({deadline.strftime('%d.%m %H:%M')})")
        send("\n".join(lines))
        return

    if text == "/cache":
        cache = QACache()
        send(f"📦 {cache.stats_line()}\n\nДля очистки: /cache_clear")
        return

    if text == "/cache_clear":
        QACache().clear()
        send("🗑️ Кэш Q&A очищен")
        return

    send("Не понял 🤔 /help")


def handle_callback(data: str, cb_id: str, chat_id: str):
    answer_callback(cb_id)

    # approve/skip/start — идут в очередь для фоновых задач
    if data in ("approve", "skip", "start"):
        callback_queue.put(data)
        return

    p = pending.get(chat_id)

    if data.startswith("sched:") and p and p["type"] == "schedule":
        subject = registry.get(data.split(":", 1)[1])
        if not subject: return
        idx = p["idx"]
        slot = p["slots"][idx]
        link = p["links"][idx] if idx < len(p["links"]) else p["links"][-1]
        event_id = link.rstrip("/").split("/")[-1]
        if event_id not in subject.event_ids:
            subject.event_ids.append(event_id)
            registry._save()
        schedule_lecture(subject, slot["start_time"], slot["duration"], event_id, link)
        _next_slot(p, chat_id)
        return

    if data == "sched_skip" and p and p["type"] == "schedule":
        _next_slot(p, chat_id)
        return

    if data.startswith("quiz:") and p and p["type"] == "quiz":
        subject = registry.get(data.split(":", 1)[1])
        if not subject: return
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
        if not subject: return
        url = p["url"]
        pending.pop(chat_id, None)
        send(f"✍️ Выполняю: <b>{subject.name}</b>")
        threading.Thread(
            target=lambda: SubjectAgent(subject).run_assignment_by_url(url),
            daemon=True
        ).start()
        return

    if data.startswith("preview:") and p and p["type"] == "preview":
        subject = registry.get(data.split(":", 1)[1])
        if not subject: return
        url = p["url"]
        pending.pop(chat_id, None)
        send(f"🔍 Dry-run: <b>{subject.name}</b>")
        is_quiz = "/mod/quiz/" in url

        def _run():
            agent = SubjectAgent(subject)
            if is_quiz:
                agent.run_quiz_by_url(url, dry_run=True)
            else:
                agent.run_assignment_by_url(url, dry_run=True)

        threading.Thread(target=_run, daemon=True).start()
        return

    if data.startswith("webinar:") and p and p["type"] == "webinar":
        subject = registry.get(data.split(":", 1)[1])
        if not subject: return
        url = p["url"]
        event_id = url.rstrip("/").split("/")[-1]
        if event_id not in subject.event_ids:
            subject.event_ids.append(event_id)
            registry._save()
        pending.pop(chat_id, None)
        send(f"🚀 Лекция: <b>{subject.name}</b>")
        threading.Thread(
            target=lambda: SubjectAgent(subject).full_cycle(event_id=event_id, webinar_url=url),
            daemon=True
        ).start()
        return


def _next_slot(p: dict, chat_id: str):
    p["idx"] += 1
    if p["idx"] < len(p["slots"]):
        slot = p["slots"][p["idx"]]
        kb = subject_keyboard("sched")
        kb.append([{"text": "⏭ Пропустить", "callback_data": "sched_skip"}])
        send(f"<b>Пара {p['idx'] + 1}:</b> {slot['start_time']} — {slot['title']}", keyboard=kb)
    else:
        pending.pop(chat_id, None)
        send("✅ Все пары запланированы")


def main():
    print("🚀 Запуск...")
    required = ["TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID", "GROQ_API_KEY"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        print(f"❌ Не заданы: {', '.join(missing)}")
        return

    threading.Thread(target=_deadline_reminder_loop, daemon=True).start()
    print("⏰ Напоминания о дедлайнах запущены")

    send("🤖 Бот запущен! /start — помощь")
    print("🤖 Ожидаю...")

    my_chat = str(_chat_id())
    offset = None

    while True:
        try:
            for update in get_updates(offset):
                offset = update["update_id"] + 1
                msg = update.get("message")
                if msg and str(msg["chat"]["id"]) == my_chat:
                    handle_message(msg)
                cb = update.get("callback_query")
                if cb and str(cb["message"]["chat"]["id"]) == my_chat:
                    handle_callback(cb["data"], cb["id"], str(cb["message"]["chat"]["id"]))
        except Exception as e:
            print(f"⚠️ {e}")
            time.sleep(5)
        time.sleep(0.5)


if __name__ == "__main__":
    main()
