"""
agent.py — основной агент.

Умеет:
- Посещать эфир и накапливать конспект
- Решать тесты с подтверждением через Telegram
- Самостоятельно находить и выполнять задания со всех курсов
"""

import time
import os
from datetime import datetime

from subjects import SubjectRegistry, Subject
from lecture_listener import LectureListener
from presence import PresenceKeeper
from smart_solver import SmartSolver
from essay_solver import EssaySolver
from browser import UniBrowser
from telegram_notifier import TelegramNotifier

NOTES_DIR = "notes"


class SubjectAgent:
    def __init__(self, subject: Subject):
        self.subject = subject
        self.registry = SubjectRegistry()
        self.tg = TelegramNotifier()

    # ─── Лекция ────────────────────────────────────────────────

    def run_lecture(self, event_id: str = None, webinar_url: str = None):
        s = self.subject
        eid = event_id or (s.event_ids[-1] if s.event_ids else None)
        url = webinar_url or s.webinar_url

        if not eid:
            self.tg.notify(f"❌ [{s.name}] Не указан ID эфира")
            return None

        self.tg.notify(f"🎓 Начинаю лекцию: <b>{s.name}</b>")

        # Используем presence как context manager — правильно работает с Playwright
        with PresenceKeeper(url):
            listener = LectureListener(eid)
            knowledge = listener.listen_realtime(s.duration_minutes)

        if knowledge.strip():
            os.makedirs(NOTES_DIR, exist_ok=True)
            date_str = datetime.now().strftime("%Y%m%d_%H%M")
            filename = f"{NOTES_DIR}/{s.subject_id}_{date_str}.txt"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"Предмет: {s.name}\n")
                f.write(f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n")
                f.write(knowledge)
            self.registry.add_notes(s.subject_id, filename)
            words = len(knowledge.split())
            self.tg.notify_lecture_done(s.name, words)
            return filename
        else:
            self.tg.notify(f"⚠️ [{s.name}] Конспект пуст — субтитры недоступны")
            return None

    # ─── Тесты ─────────────────────────────────────────────────

    def run_quiz_by_url(self, quiz_url: str):
        """Решает один конкретный тест с подтверждением через Telegram."""
        s = self.subject
        knowledge = s.get_full_knowledge()
        solver = SmartSolver(knowledge)

        self.tg.notify(f"📝 Открываю тест по <b>{s.name}</b>...")
        bot = UniBrowser(headless=True)

        try:
            bot.login()
            bot.goto(quiz_url)
            bot.start_quiz()

            questions = bot.get_quiz_data()
            if not questions:
                self.tg.notify(f"⚠️ [{s.name}] Вопросы не найдены на странице")
                return

            answers, confidences = solver.solve_all(questions)

            # Кликаем ответы на странице
            for q, idx in zip(questions, answers):
                elements = q.get("elements", [])
                if elements and idx < len(elements):
                    bot.click_answer(elements[idx])

            # Подтверждение через Telegram
            result = self.tg.confirm_quiz(s.name, questions, answers, confidences)

            if result == "approve":
                bot.submit_quiz()
                self.tg.notify(f"✅ Тест сдан: <b>{s.name}</b>")
            else:
                self.tg.notify(f"⏭ Тест пропущен: <b>{s.name}</b>")

        except Exception as e:
            self.tg.notify_error(s.name, f"Ошибка теста: {e}")
        finally:
            bot.close()

    def run_quizzes(self):
        """Проходит все сохранённые тесты по предмету."""
        for quiz_url in self.subject.quiz_urls:
            self.run_quiz_by_url(quiz_url)
            time.sleep(3)

    # ─── Задания ───────────────────────────────────────────────

    def run_assignment_by_url(self, assignment_url: str):
        """Читает требования и пишет ответ с подтверждением через Telegram."""
        s = self.subject
        knowledge = s.get_full_knowledge()
        essay_solver = EssaySolver(knowledge)

        self.tg.notify(f"✍️ Открываю задание по <b>{s.name}</b>...")
        bot = UniBrowser(headless=True)

        try:
            bot.login()
            bot.goto(assignment_url)

            task_text = bot.get_task_text()
            if not task_text:
                self.tg.notify(f"⚠️ [{s.name}] Не нашёл текст задания")
                return

            answer = essay_solver.write_essay(task_text)
            if not answer:
                self.tg.notify(f"⚠️ [{s.name}] Не удалось сгенерировать ответ")
                return

            # Подтверждение через Telegram
            confidence = 0.8 if knowledge.strip() else 0.5
            result = self.tg.confirm_assignment(s.name, task_text, answer, confidence)

            if result == "approve":
                # Открываем редактор ответа если нужно
                bot.open_assignment_editor()
                time.sleep(1)
                bot.fill_text_answer(answer)
                time.sleep(1)
                bot.submit_assignment()
                self.tg.notify(f"✅ Задание сдано: <b>{s.name}</b>")
            else:
                self.tg.notify(f"⏭ Задание пропущено: <b>{s.name}</b>")

        except Exception as e:
            self.tg.notify_error(s.name, f"Ошибка задания: {e}")
        finally:
            bot.close()

    def run_assignments(self):
        """Выполняет все сохранённые задания по предмету."""
        for url in self.subject.assignment_urls:
            self.run_assignment_by_url(url)
            time.sleep(3)

    # ─── Полный цикл ───────────────────────────────────────────

    def full_cycle(self, event_id: str = None, webinar_url: str = None):
        """Лекция → тесты → задания."""
        self.tg.notify(f"🚀 Начинаю цикл: <b>{self.subject.name}</b>")
        self.run_lecture(event_id, webinar_url)
        time.sleep(5)
        self.run_quizzes()
        self.run_assignments()
        self.tg.notify(f"✅ Цикл завершён: <b>{self.subject.name}</b>")


# ─── Функции для работы со всеми предметами ────────────────────

def scan_all_courses():
    """
    Сам заходит на сайт, находит все курсы, читает требования всех заданий
    и создаёт/обновляет предметы в реестре.
    """
    tg = TelegramNotifier()
    registry = SubjectRegistry()
    tg.notify("🔍 Сканирую все курсы на сайте...")

    bot = UniBrowser(headless=True)
    total_quizzes = 0
    total_assignments = 0

    try:
        bot.login()
        courses = bot.get_my_courses()

        if not courses:
            tg.notify("⚠️ Курсы не найдены на сайте")
            return

        tg.notify(f"📚 Найдено курсов: <b>{len(courses)}</b>")

        for course in courses:
            name = course["name"]
            url = course["url"]
            subject_id = _slugify(name)

            # Создаём или обновляем предмет
            subject = registry.get(subject_id)
            if not subject:
                subject = Subject(name=name, subject_id=subject_id)
                registry.add(subject)

            # Заходим на страницу курса и собираем активности
            try:
                bot.goto(url)
                activities = bot.get_course_activities()

                quiz_urls = [a["url"] for a in activities if a["type"] == "quiz"]
                assignment_urls = [a["url"] for a in activities if a["type"] == "assignment"]
                video_urls = [a["url"] for a in activities if a["type"] == "video"]

                # Обновляем ссылки (только новые)
                for q_url in quiz_urls:
                    if q_url not in subject.quiz_urls:
                        subject.quiz_urls.append(q_url)
                for a_url in assignment_urls:
                    if a_url not in subject.assignment_urls:
                        subject.assignment_urls.append(a_url)
                if video_urls and not subject.webinar_url:
                    subject.webinar_url = video_urls[0]

                registry._save()
                total_quizzes += len(quiz_urls)
                total_assignments += len(assignment_urls)

                print(f"  [{name}] тестов: {len(quiz_urls)}, заданий: {len(assignment_urls)}")
            except Exception as e:
                print(f"⚠️ Ошибка в курсе {name}: {e}")

        tg.notify(
            f"✅ Сканирование завершено\n"
            f"Курсов: <b>{len(courses)}</b>\n"
            f"Тестов: <b>{total_quizzes}</b>\n"
            f"Заданий: <b>{total_assignments}</b>"
        )
    except Exception as e:
        tg.notify_error("Сканирование", str(e))
    finally:
        bot.close()


def run_all_assignments():
    """Проходит все задания по всем предметам с подтверждением."""
    registry = SubjectRegistry()
    for subject in registry.all():
        if subject.assignment_urls:
            agent = SubjectAgent(subject)
            agent.run_assignments()


def run_all_quizzes():
    """Проходит все тесты по всем предметам с подтверждением."""
    registry = SubjectRegistry()
    for subject in registry.all():
        if subject.quiz_urls:
            agent = SubjectAgent(subject)
            agent.run_quizzes()


def _slugify(name: str) -> str:
    """Преобразует название предмета в короткий ID."""
    import re
    import hashlib
    # Берём первые 20 символов + хэш для уникальности
    cleaned = re.sub(r'[^a-zа-я0-9]', '_', name.lower())[:20]
    cleaned = re.sub(r'_+', '_', cleaned).strip('_')
    if not cleaned:
        cleaned = "course"
    # Добавляем короткий хэш чтобы ID были уникальными
    h = hashlib.md5(name.encode()).hexdigest()[:4]
    return f"{cleaned}_{h}"
