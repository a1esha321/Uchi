"""
navigator.py — автономная навигация по campus.fa.ru.

Полный цикл:
1. Читает дедлайны из календаря — знает что срочно
2. Обходит ВСЕ курсы (с пагинацией)
3. На каждом курсе находит тесты
4. Решает тесты используя знания из конспектов
5. Запоминает что уже решено
"""

import time, json, os
from browser import UniBrowser
from smart_solver import SmartSolver
from subjects import SubjectRegistry

COMPLETED_FILE = "completed_tasks.json"


class Navigator:
    def __init__(self, headless: bool = False):
        self.bot = UniBrowser(headless=headless)
        self.registry = SubjectRegistry()
        self.completed = self._load_completed()

    # ─── ПАМЯТЬ ───────────────────────────────────────────────

    def _load_completed(self) -> set:
        if os.path.exists(COMPLETED_FILE):
            with open(COMPLETED_FILE, "r") as f:
                return set(json.load(f))
        return set()

    def _mark_completed(self, url: str):
        self.completed.add(url)
        with open(COMPLETED_FILE, "w") as f:
            json.dump(list(self.completed), f)

    def _is_completed(self, url: str) -> bool:
        return url in self.completed

    # ─── ГЛАВНЫЙ ОБХОД ────────────────────────────────────────

    def run_full_scan(self):
        """
        Полный автономный обход campus.fa.ru:
        - Читает дедлайны из календаря
        - Обходит все курсы (все страницы пагинации)
        - Решает все найденные тесты
        """
        print("\n" + "="*55)
        print("🤖 АВТОНОМНЫЙ ОБХОД campus.fa.ru")
        print("="*55)

        # 1. Логин
        self.bot.login()

        # 2. Читаем дедлайны из календаря
        print("\n📅 Проверяю дедлайны...")
        deadlines = self.bot.get_upcoming_deadlines()
        if deadlines:
            print("⚠️  Ближайшие дедлайны:")
            for d in deadlines[:5]:
                print(f"   • {d[:80]}")

        # 3. Получаем ВСЕ курсы (с пагинацией)
        print("\n📚 Собираю список курсов...")
        courses = self.bot.get_my_courses()

        if not courses:
            print("❌ Курсы не найдены")
            self.bot.close()
            return

        total_quizzes = 0

        # 4. Обходим каждый курс
        for i, course in enumerate(courses):
            print(f"\n[{i+1}/{len(courses)}] 📖 {course['name']}")
            self.bot.goto(course["url"])
            time.sleep(1)

            # 5. Сканируем активности курса
            activities = self.bot.get_course_activities()
            quizzes = [a for a in activities if a["type"] == "quiz"
                      and not self._is_completed(a["url"])]

            if not quizzes:
                print("  ✓ Новых тестов нет")
                continue

            print(f"  🧪 Новых тестов: {len(quizzes)}")

            # 6. Загружаем знания по этому предмету
            knowledge = self._get_knowledge(course["name"])

            # 7. Решаем каждый тест
            for quiz in quizzes:
                print(f"\n  📝 {quiz['name']}")
                self._solve_quiz(quiz["url"], knowledge)
                total_quizzes += 1
                time.sleep(2)

            # 8. Проверяем ссылки на Степик
            self._handle_stepik_links(knowledge)

        print("\n" + "="*55)
        print(f"✅ Обход завершён! Решено тестов: {total_quizzes}")
        print("="*55)
        self.bot.close()

    # ─── РЕШЕНИЕ ТЕСТА ────────────────────────────────────────

    def _solve_quiz(self, quiz_url: str, knowledge: str):
        try:
            self.bot.goto(quiz_url)

            # Нажимаем "Начать тестирование"
            started = self.bot.start_quiz()
            if not started:
                # Тест уже начат или нет кнопки — пробуем читать вопросы напрямую
                pass

            questions = self.bot.get_quiz_data()
            if not questions:
                print("  ⚠️ Вопросы не найдены")
                return

            solver = SmartSolver(knowledge)
            answers = solver.solve_all(questions)

            for q, idx in zip(questions, answers):
                if q["type"] == "text":
                    # Текстовый ответ
                    text_answer = solver.solve_question(q["question"], [])
                    q["elements"][0].fill(str(text_answer))
                else:
                    self.bot.click_answer(q["elements"][idx])

            time.sleep(1)
            self.bot.submit_quiz()
            self._mark_completed(quiz_url)
            print(f"  ✅ Тест сдан!")

        except Exception as e:
            print(f"  ❌ Ошибка: {e}")

    # ─── СТЕПИК ───────────────────────────────────────────────

    def _handle_stepik_links(self, knowledge: str):
        stepik_els = self.bot.page.query_selector_all('a[href*="stepik.org"]')
        if not stepik_els:
            return

        print(f"\n  🔗 Найдено ссылок на Степик: {len(stepik_els)}")
        from stepik import StepikAgent
        agent = StepikAgent(headless=False, knowledge=knowledge)

        try:
            agent.login()
            for el in stepik_els:
                url = el.get_attribute("href")
                if url and not self._is_completed(url):
                    print(f"  📚 Степик: {url}")
                    agent.complete_course(url)
                    self._mark_completed(url)
        finally:
            agent.close()

    # ─── ЗНАНИЯ ───────────────────────────────────────────────

    def _get_knowledge(self, course_name: str) -> str:
        """Ищет конспекты лекций для данного курса"""
        name_lower = course_name.lower()

        # Убираем суффиксы типа "_ДИРПО25-1_1_сем"
        clean_name = name_lower.split("_дирпо")[0].split("_дбани")[0].strip()

        for subject in self.registry.all():
            subj_lower = subject.name.lower()
            if subj_lower in clean_name or clean_name in subj_lower:
                knowledge = subject.get_full_knowledge()
                if knowledge:
                    print(f"  📚 Знания: {subject.name}")
                    return knowledge

        return ""  # Без конспекта — Claude отвечает из общих знаний
