"""
agent.py — главный агент. Лекция → тест/задание.
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

NOTES_DIR = "notes"


class SubjectAgent:
    def __init__(self, subject: Subject):
        self.subject = subject
        self.registry = SubjectRegistry()

    def run_lecture(self, event_id: str = None):
        s = self.subject
        eid = event_id or (s.event_ids[-1] if s.event_ids else None)
        if not eid:
            print(f"[{s.name}] Не указан event_id")
            return None

        print(f"\n=== ЛЕКЦИЯ: {s.name} ===")

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
            print(f"✅ [{s.name}] Конспект сохранён: {words} слов → {filename}")
            return filename
        else:
            print(f"⚠️ [{s.name}] Субтитры недоступны")
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

                questions = bot.get_quiz_data()
                if not questions:
                    print("Вопросы не найдены")
                    continue

                answers, confidences = solver.solve_all(questions)

                for q, idx in zip(questions, answers):
                    bot.click_answer(q["elements"][idx])

                time.sleep(1)
                bot.submit_quiz()
                print(f"✅ Тест сдан: {s.name}")

            except Exception as e:
                print(f"❌ Ошибка теста [{s.name}]: {e}")
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
                bot.fill_text_answer(answer)
                time.sleep(1)
                bot.submit_assignment()
                print(f"✅ Задание сдано: {s.name}")

            except Exception as e:
                print(f"❌ Ошибка задания [{s.name}]: {e}")
            finally:
                bot.close()
                time.sleep(2)

    def full_cycle(self, event_id: str = None):
        print(f"\nЦикл: {self.subject.name}")
        self.run_lecture(event_id)
        time.sleep(10)
        self.run_quizzes()
        self.run_assignments()
        print(f"✅ Цикл завершён: {self.subject.name}")
