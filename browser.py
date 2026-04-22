"""
browser.py — управление браузером для campus.fa.ru (Moodle).
Работает через sync_playwright, но БЕЗ input() — подтверждение идёт через Telegram.
"""

import os
import time
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv()


class UniBrowser:
    def __init__(self, headless: bool = True):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ]
        )
        self.context = self.browser.new_context()
        self.page = self.context.new_page()

    # ─── Авторизация ──────────────────────────────────────────

    def login(self):
        uni_url = os.getenv("UNI_URL", "https://campus.fa.ru/login/index.php")
        login_val = os.getenv("UNI_LOGIN")
        password_val = os.getenv("UNI_PASSWORD")

        if not login_val or not password_val:
            raise ValueError("UNI_LOGIN или UNI_PASSWORD не заданы в переменных окружения")

        self.page.goto(uni_url, timeout=60000)
        self.page.wait_for_load_state("networkidle")

        # Универсальный поиск полей
        username_field = (
            self.page.query_selector('input[name="username"]') or
            self.page.query_selector('input[id="username"]') or
            self.page.query_selector('input[type="text"]')
        )
        password_field = (
            self.page.query_selector('input[name="password"]') or
            self.page.query_selector('input[id="password"]') or
            self.page.query_selector('input[type="password"]')
        )

        if not username_field or not password_field:
            raise RuntimeError("Не нашёл поля логина на странице")

        username_field.fill(login_val)
        password_field.fill(password_val)

        submit_btn = (
            self.page.query_selector('#loginbtn') or
            self.page.query_selector('button[type="submit"]') or
            self.page.query_selector('input[type="submit"]')
        )
        if submit_btn:
            submit_btn.click()

        self.page.wait_for_load_state("networkidle", timeout=30000)
        print("✅ Авторизация на сайте")

    def goto(self, url: str):
        self.page.goto(url, timeout=60000)
        self.page.wait_for_load_state("networkidle")
        time.sleep(2)

    # ─── Курсы ─────────────────────────────────────────────────

    def get_my_courses(self) -> list:
        """Собирает список всех доступных курсов студента."""
        uni_url = os.getenv("UNI_URL", "https://campus.fa.ru")
        base = uni_url.split("/login")[0].rstrip("/")
        self.page.goto(f"{base}/my/courses.php", timeout=60000)
        self.page.wait_for_load_state("networkidle")
        time.sleep(2)

        courses = []
        seen_urls = set()

        course_els = self.page.query_selector_all(
            '.coursename a, a[href*="/course/view.php"]'
        )

        for el in course_els:
            href = el.get_attribute("href") or ""
            name = el.inner_text().strip()
            if href and "course/view.php" in href and href not in seen_urls and name:
                courses.append({"name": name, "url": href})
                seen_urls.add(href)

        print(f"📚 Найдено курсов: {len(courses)}")
        return courses

    def get_course_activities(self) -> list:
        """Сканирует страницу курса — находит все тесты, задания, видео."""
        activities = []
        seen = set()

        all_links = self.page.query_selector_all(
            '.activityinstance a, .activity a.aalink, li.activity a[href*="/mod/"]'
        )

        for el in all_links:
            href = el.get_attribute("href") or ""
            if not href or href in seen:
                continue
            name = el.inner_text().strip() or "Без названия"

            if "/mod/quiz/" in href:
                atype = "quiz"
            elif "/mod/url/" in href or "mts-link" in href:
                atype = "video"
            elif "/mod/resource/" in href:
                atype = "pdf"
            elif "/mod/assign/" in href:
                atype = "assignment"
            else:
                atype = "other"

            activities.append({"type": atype, "name": name, "url": href})
            seen.add(href)

        return activities

    # ─── Тесты ────────────────────────────────────────────────

    def start_quiz(self) -> bool:
        """Нажимает кнопку 'Начать тестирование' если она есть."""
        btn = (
            self.page.query_selector('button:has-text("Начать тестирование")') or
            self.page.query_selector('a:has-text("Начать тестирование")') or
            self.page.query_selector('input[value="Начать тестирование"]')
        )
        if btn:
            btn.click()
            self.page.wait_for_load_state("networkidle")
            time.sleep(2)
            confirm = self.page.query_selector('button:has-text("Начать попытку")')
            if confirm:
                confirm.click()
                self.page.wait_for_load_state("networkidle")
                time.sleep(2)
            print("✅ Тест начат")
            return True
        return False

    def get_quiz_data(self) -> list:
        """Извлекает вопросы и варианты ответов со страницы теста."""
        questions = []
        question_blocks = self.page.query_selector_all(".que")

        for block in question_blocks:
            q_el = block.query_selector(".qtext")
            if not q_el:
                continue
            question_text = q_el.inner_text().strip()

            radios = block.query_selector_all('.answer input[type="radio"]')
            checkboxes = block.query_selector_all('.answer input[type="checkbox"]')

            if radios:
                labels = block.query_selector_all('.answer label')
                options = [l.inner_text().strip() for l in labels]
                questions.append({
                    "question": question_text, "type": "radio",
                    "options": options, "elements": list(radios)
                })
            elif checkboxes:
                labels = block.query_selector_all('.answer label')
                options = [l.inner_text().strip() for l in labels]
                questions.append({
                    "question": question_text, "type": "checkbox",
                    "options": options, "elements": list(checkboxes)
                })

        print(f"  📋 Вопросов найдено: {len(questions)}")
        return questions

    def click_answer(self, element):
        """Кликает на элемент ответа."""
        try:
            element.click()
            time.sleep(0.3)
        except Exception as e:
            print(f"  ⚠️ Не смог кликнуть: {e}")

    def submit_quiz(self):
        """Завершает тест — отправляет ответы."""
        finish = (
            self.page.query_selector('input[value="Закончить попытку"]') or
            self.page.query_selector('button:has-text("Закончить попытку")')
        )
        if finish:
            finish.click()
            self.page.wait_for_load_state("networkidle")
            time.sleep(2)

        submit = (
            self.page.query_selector('input[value="Отправить всё и завершить тест"]') or
            self.page.query_selector('button:has-text("Отправить всё и завершить тест")')
        )
        if submit:
            submit.click()
            time.sleep(2)

        confirm = self.page.query_selector('.modal-footer button.btn-primary')
        if confirm:
            confirm.click()
            self.page.wait_for_load_state("networkidle")

        print("  ✅ Тест отправлен")

    # ─── Задания ──────────────────────────────────────────────

    def get_task_text(self) -> str:
        """Читает требования преподавателя со страницы задания."""
        task_el = (
            self.page.query_selector(".box.generalbox") or
            self.page.query_selector("#intro") or
            self.page.query_selector('[role="main"]')
        )
        if task_el:
            text = task_el.inner_text().strip()
            print(f"📄 Прочитано требований: {len(text)} симв.")
            return text
        return ""

    def open_assignment_editor(self):
        """Открывает редактор ответа (кнопка 'Добавить ответ на задание')."""
        btn = (
            self.page.query_selector('button:has-text("Добавить ответ")') or
            self.page.query_selector('a:has-text("Добавить ответ")') or
            self.page.query_selector('input[value*="ответ"]')
        )
        if btn:
            btn.click()
            self.page.wait_for_load_state("networkidle")
            time.sleep(2)
            return True
        return False

    def fill_text_answer(self, text: str):
        """Вставляет текст ответа в поле редактора."""
        iframe = self.page.query_selector('iframe[id*="editor"], iframe.cke_wysiwyg_frame')
        if iframe:
            frame = iframe.content_frame()
            if frame:
                body = frame.query_selector("body")
                if body:
                    body.fill(text)
                    print("✅ Ответ вставлен в iframe")
                    return

        textarea = self.page.query_selector("textarea")
        if textarea:
            textarea.fill(text)
            print("✅ Ответ вставлен в textarea")
            return

        editable = self.page.query_selector('[contenteditable="true"]')
        if editable:
            editable.click()
            editable.fill(text)
            print("✅ Ответ вставлен в contenteditable")

    def submit_assignment(self):
        """Сохраняет/отправляет задание."""
        btn = (
            self.page.query_selector('input[value="Сохранить изменения"]') or
            self.page.query_selector('button:has-text("Сохранить")') or
            self.page.query_selector('button[type="submit"]')
        )
        if btn:
            btn.click()
            self.page.wait_for_load_state("networkidle")
            print("  ✅ Задание сохранено")

    # ─── Закрытие ─────────────────────────────────────────────

    def close(self):
        try:
            self.context.close()
            self.browser.close()
            self.playwright.stop()
        except Exception:
            pass
