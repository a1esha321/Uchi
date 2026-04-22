"""
agent.py — главный агент. Лекция → тест/задание → Telegram подтверждение.
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

    def run_lecture(self, event_id: str = None):
        s = self.subject
        eid = event_id or (s.event_ids[-1] if s.event_ids else None)
        if not eid:
            print(f"[{s.name}] Не указан event_id")
            return None

        print(f"\n=== ЛЕКЦИЯ: {s.name} ===")
        self.tg.notify(f"Начинаю лекцию: <b>{s.name}</b>")

        presence = PresenceKeeper(s.webinar_url)
        presence.start()

        listener = LectureListener(eid)
        knowledge = listener.listen_realtime(s.duration_minutes)

        presence.stop()

        if knowledge.strip():
            os.makedirs(NOTES_DIR, exist_ok=True)
            date_str = datetime.now().strftime("%Y%m%d_%H%M")
            filename = f"{NOTES_DIR}/{s.subject_id}_{date_str}.txt"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"Предмет: {s.name}\nДата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n")
                f.write(knowledge)
            self.registry.add_notes(s.subject_id, filename)
            words = len(knowledge.split())
            self.tg.notify_lecture_done(s.name, words, filename)
            return filename
        else:
            self.tg.notify(f"<b>{s.name}</b>: субтитры недоступны")
            return None

    def run_quizzes(self):
        s = self.subject
        if not s.quiz_urls:
            return

        knowledge = s.get_full_knowledge()
        solver = SmartSolver(knowledge)

        for quiz_url in s.quiz_urls:
            print(f"\nТест: {quiz_url}")
            bot = UniBrowser(headless=True)
            try:
                bot.login()
                bot.goto(quiz_url)
                bot.start_quiz()

                questions = bot.get_quiz_data()
                if not questions:
                    print("Вопросы не найдены")
                    continue

                answers, confidences = solver.solve_all(questions)

                for q, idx in zip(questions, answers):
                    bot.click_answer(q["elements"][idx])

                result = self.tg.confirm_quiz(s.name, questions, answers, confidences)

                if result == "approve":
                    bot.submit_quiz()
                    print(f"Тест отправлен: {s.name}")
                else:
                    print(f"Тест пропущен: {s.name}")

            except Exception as e:
                print(f"Ошибка теста [{s.name}]: {e}")
                self.tg.notify_error(s.name, str(e))
            finally:
                bot.close()
                time.sleep(2)

    def run_assignments(self):
        s = self.subject
        if not s.assignment_urls:
            return

        knowledge = s.get_full_knowledge()
        essay_solver = EssaySolver(knowledge)

        for url in s.assignment_urls:
            print(f"\nЗадание: {url}")
            bot = UniBrowser(headless=True)
            try:
                bot.login()
                bot.goto(url)

                task_text = bot.get_task_text()
                if not task_text:
                    print("Текст задания не найден")
                    continue

                answer = essay_solver.write_essay(task_text)
                confidence = 0.75 if knowledge.strip() else 0.45

                result = self.tg.confirm_assignment(s.name, task_text, answer, confidence)

                if result == "approve":
                    bot.fill_text_answer(answer)
                    time.sleep(1)
                    bot.submit_assignment()
                else:
                    print(f"Задание пропущено: {s.name}")

            except Exception as e:
                print(f"Ошибка задания [{s.name}]: {e}")
                self.tg.notify_error(s.name, str(e))
            finally:
                bot.close()
                time.sleep(2)

    def full_cycle(self, event_id: str = None):
        print(f"\nЦикл: {self.subject.name}")
        self.run_lecture(event_id)
        time.sleep(10)
        self.run_quizzes()
        self.run_assignments()
        self.tg.notify(f"Цикл завершён: <b>{self.subject.name}</b>")
