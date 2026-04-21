"""
stepik.py — агент для прохождения курсов на Stepik.org.

Умеет:
- Логиниться на Степик
- Находить курс по ссылке
- Проходить все уроки по порядку
- Решать тесты с вариантами ответов
- Отвечать на текстовые вопросы
- Решать задачи с кодом
- Отмечать уроки как просмотренные

Использование:
    agent = StepikAgent()
    agent.login()
    agent.complete_course("https://stepik.org/course/12345")
"""

import time
import os
import anthropic
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

STEPIK_LOGIN = os.getenv("STEPIK_LOGIN")    # добавь в .env
STEPIK_PASSWORD = os.getenv("STEPIK_PASSWORD")  # добавь в .env


class StepikAgent:
    def __init__(self, headless: bool = False, knowledge: str = ""):
        """
        headless   — False = видишь браузер, True = фоновый режим
        knowledge  — конспект лекций для контекста (опционально)
        """
        self.knowledge = knowledge
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=headless)
        self.page = self.browser.new_page()

    # ─── АВТОРИЗАЦИЯ ──────────────────────────────────────────

    def login(self):
        """Логинимся на Степик"""
        print("🔐 Захожу на Степик...")
        self.page.goto("https://stepik.org/login")
        self.page.wait_for_load_state("networkidle")

        self.page.fill('input[name="login"]', STEPIK_LOGIN)
        self.page.fill('input[name="password"]', STEPIK_PASSWORD)
        self.page.click('button[type="submit"]')
        self.page.wait_for_load_state("networkidle")
        time.sleep(2)
        print("✅ Залогинились на Степик")

    # ─── КУРС ─────────────────────────────────────────────────

    def complete_course(self, course_url: str):
        """
        Полностью проходит курс по ссылке.
        Обходит все модули и уроки по порядку.
        """
        print(f"\n📚 Начинаю курс: {course_url}")
        self.page.goto(course_url)
        self.page.wait_for_load_state("networkidle")
        time.sleep(2)

        # Находим кнопку "Начать обучение" / "Продолжить"
        start_btn = (
            self.page.query_selector('a:has-text("Начать обучение")') or
            self.page.query_selector('a:has-text("Продолжить")') or
            self.page.query_selector('a:has-text("Continue")')
        )
        if start_btn:
            start_btn.click()
            self.page.wait_for_load_state("networkidle")
            time.sleep(2)

        # Собираем все ссылки на уроки
        lesson_links = self._get_all_lessons(course_url)
        print(f"📋 Найдено уроков: {len(lesson_links)}")

        completed = 0
        for i, lesson_url in enumerate(lesson_links):
            print(f"\n[{i+1}/{len(lesson_links)}] Урок: {lesson_url}")
            self._complete_lesson(lesson_url)
            completed += 1
            time.sleep(2)

        print(f"\n🎉 Курс завершён! Пройдено уроков: {completed}")

    def _get_all_lessons(self, course_url: str) -> list[str]:
        """Собирает ссылки на все уроки курса"""
        self.page.goto(course_url)
        time.sleep(2)

        links = []
        lesson_els = self.page.query_selector_all('a[href*="/lesson/"]')

        for el in lesson_els:
            href = el.get_attribute("href") or ""
            if href.startswith("/"):
                href = "https://stepik.org" + href
            if href and href not in links:
                links.append(href)

        return links

    # ─── УРОК ─────────────────────────────────────────────────

    def _complete_lesson(self, lesson_url: str):
        """Проходит один урок — все шаги внутри"""
        self.page.goto(lesson_url)
        self.page.wait_for_load_state("networkidle")
        time.sleep(3)

        step = 1
        while True:
            print(f"  📄 Шаг {step}")
            completed = self._complete_current_step()

            if not completed:
                print(f"  ⚠️ Не удалось пройти шаг {step}")

            # Переходим к следующему шагу
            next_btn = (
                self.page.query_selector('button:has-text("Следующий шаг")') or
                self.page.query_selector('button:has-text("Next")') or
                self.page.query_selector('.lesson__next-btn')
            )

            if next_btn and next_btn.is_enabled():
                next_btn.click()
                self.page.wait_for_load_state("networkidle")
                time.sleep(2)
                step += 1
            else:
                print(f"  ✅ Урок завершён ({step} шагов)")
                break

    # ─── ШАГ (определяем тип и решаем) ────────────────────────

    def _complete_current_step(self) -> bool:
        """
        Определяет тип текущего шага и решает его.
        Возвращает True если успешно.
        """
        time.sleep(1)

        # Тип 1: Видео / текст — просто отмечаем как просмотренное
        if self._is_video_or_text_step():
            return self._complete_view_step()

        # Тип 2: Тест с вариантами ответов
        if self._is_choice_step():
            return self._solve_choice_step()

        # Тип 3: Текстовый / числовой ответ
        if self._is_text_step():
            return self._solve_text_step()

        # Тип 4: Задача с кодом
        if self._is_code_step():
            return self._solve_code_step()

        # Неизвестный тип — пробуем нажать "Отправить"
        return self._try_submit()

    # ─── ОПРЕДЕЛЕНИЕ ТИПА ШАГА ────────────────────────────────

    def _is_video_or_text_step(self) -> bool:
        return bool(
            self.page.query_selector('video') or
            self.page.query_selector('.video-js') or
            (not self.page.query_selector('.submit-submission') and
             not self.page.query_selector('textarea') and
             not self.page.query_selector('.CodeMirror'))
        )

    def _is_choice_step(self) -> bool:
        return bool(
            self.page.query_selector('input[type="radio"]') or
            self.page.query_selector('input[type="checkbox"]')
        )

    def _is_text_step(self) -> bool:
        return bool(
            self.page.query_selector('input[type="text"].ember-text-field') or
            self.page.query_selector('.text-input')
        )

    def _is_code_step(self) -> bool:
        return bool(
            self.page.query_selector('.CodeMirror') or
            self.page.query_selector('textarea[class*="code"]')
        )

    # ─── РЕШЕНИЕ КАЖДОГО ТИПА ─────────────────────────────────

    def _complete_view_step(self) -> bool:
        """Видео/текст — ждём и идём дальше"""
        print("  👁️  Просматриваю материал...")

        # Если есть видео — ждём дольше (имитируем просмотр)
        if self.page.query_selector('video'):
            time.sleep(10)
        else:
            time.sleep(3)

        # Нажимаем кнопку завершения если есть
        done_btn = (
            self.page.query_selector('button:has-text("Отправить")') or
            self.page.query_selector('button:has-text("Submit")')
        )
        if done_btn:
            done_btn.click()
            time.sleep(2)

        return True

    def _solve_choice_step(self) -> bool:
        """Тест с вариантами — Claude выбирает правильный"""
        print("  🧠 Решаю тест с вариантами...")

        # Читаем вопрос
        question_el = (
            self.page.query_selector('.question-header') or
            self.page.query_selector('.step-text') or
            self.page.query_selector('p')
        )
        question = question_el.inner_text().strip() if question_el else "Вопрос не найден"

        # Читаем варианты
        is_multi = bool(self.page.query_selector('input[type="checkbox"]'))
        selector = 'input[type="checkbox"]' if is_multi else 'input[type="radio"]'

        inputs = self.page.query_selector_all(selector)
        labels = self.page.query_selector_all('.choice__text, .option-label, label')

        options = []
        for i, inp in enumerate(inputs):
            label = labels[i] if i < len(labels) else None
            text = label.inner_text().strip() if label else f"Вариант {i+1}"
            options.append({"text": text, "input": inp})

        if not options:
            return False

        # Спрашиваем Claude
        chosen_indices = self._ask_claude_choice(question, [o["text"] for o in options], is_multi)

        # Кликаем нужные варианты
        for idx in chosen_indices:
            if 0 <= idx < len(options):
                options[idx]["input"].click()
                time.sleep(0.3)

        # Отправляем
        return self._try_submit()

    def _solve_text_step(self) -> bool:
        """Текстовый/числовой ответ"""
        print("  ✍️  Решаю текстовый вопрос...")

        question_el = self.page.query_selector('.step-text, .question-header, p')
        question = question_el.inner_text().strip() if question_el else ""

        answer = self._ask_claude_text(question)

        text_input = (
            self.page.query_selector('input[type="text"]') or
            self.page.query_selector('textarea:not([class*="code"])')
        )
        if text_input:
            text_input.fill(answer)

        return self._try_submit()

    def _solve_code_step(self) -> bool:
        """Задача с кодом — Claude пишет решение"""
        print("  💻 Решаю задачу с кодом...")

        # Читаем условие задачи
        task_el = self.page.query_selector('.step-text, .problem-statement')
        task_text = task_el.inner_text().strip() if task_el else ""

        # Определяем язык
        lang_el = self.page.query_selector('.language-select, select[name="language"]')
        language = lang_el.inner_text().strip() if lang_el else "Python"

        # Claude пишет код
        code = self._ask_claude_code(task_text, language)

        # Вставляем в редактор
        editor = self.page.query_selector('.CodeMirror')
        if editor:
            editor.click()
            # Выделяем всё и заменяем
            self.page.keyboard.press("Control+a")
            self.page.keyboard.type(code)
        else:
            textarea = self.page.query_selector('textarea')
            if textarea:
                textarea.fill(code)

        return self._try_submit()

    def _try_submit(self) -> bool:
        """Нажимаем кнопку отправки"""
        submit_btn = (
            self.page.query_selector('button.submit-submission') or
            self.page.query_selector('button:has-text("Отправить")') or
            self.page.query_selector('button:has-text("Submit")')
        )
        if submit_btn and submit_btn.is_enabled():
            submit_btn.click()
            time.sleep(3)
            return True
        return False

    # ─── ЗАПРОСЫ К CLAUDE ─────────────────────────────────────

    def _ask_claude_choice(self, question: str, options: list[str], is_multi: bool) -> list[int]:
        """Возвращает список индексов правильных ответов"""
        options_text = "\n".join([f"{i+1}. {o}" for i, o in enumerate(options)])
        mode = "несколько вариантов (через запятую)" if is_multi else "один вариант (одну цифру)"

        context = f"\nКонтекст из лекции:\n{self.knowledge[:3000]}" if self.knowledge else ""

        prompt = f"""Вопрос на Степике:{context}

{question}

Варианты:
{options_text}

Выбери {mode}. Ответь ТОЛЬКО цифрами, например: 2 или 1,3"""

        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=20,
            messages=[{"role": "user", "content": prompt}]
        )
        text = msg.content[0].text.strip()

        indices = []
        for part in text.replace(" ", "").split(","):
            if part.isdigit():
                idx = int(part) - 1
                if 0 <= idx < len(options):
                    indices.append(idx)

        return indices if indices else [0]

    def _ask_claude_text(self, question: str) -> str:
        """Возвращает короткий текстовый ответ"""
        context = f"\nКонтекст:\n{self.knowledge[:3000]}" if self.knowledge else ""

        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            messages=[{"role": "user", "content": f"{context}\n\nОтветь кратко на вопрос: {question}"}]
        )
        return msg.content[0].text.strip()

    def _ask_claude_code(self, task: str, language: str) -> str:
        """Возвращает код-решение"""
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": f"Напиши решение на {language}. Только код, без объяснений:\n\n{task}"}]
        )
        code = msg.content[0].text.strip()
        # Убираем markdown блоки если есть
        if "```" in code:
            lines = code.split("\n")
            code = "\n".join(l for l in lines if not l.startswith("```"))
        return code.strip()

    def close(self):
        self.browser.close()
        self.playwright.stop()
