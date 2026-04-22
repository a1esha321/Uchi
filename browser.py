"""
browser.py — управление браузером для campus.fa.ru (Moodle).
С поддержкой shortanswer-тестов, определением состояния и парсингом требований.
"""

import os
import re
import time
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv()


# Платформы которые бот НЕ умеет обрабатывать (другие сайты)
EXTERNAL_DOMAINS = [
    "online.fa.ru",
    "stepik.org",
    "coursera.org",
    "openedu.ru",
    "lektorium.tv",
]


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
            raise ValueError("UNI_LOGIN или UNI_PASSWORD не заданы")

        self.page.goto(uni_url, timeout=60000)
        self.page.wait_for_load_state("networkidle")

        username_field = (
            self.page.query_selector('input[name="username"]') or
            self.page.query_selector('input[id="username"]')
        )
        password_field = (
            self.page.query_selector('input[name="password"]') or
            self.page.query_selector('input[id="password"]')
        )

        if not username_field or not password_field:
            raise RuntimeError("Не нашёл поля логина")

        username_field.fill(login_val)
        password_field.fill(password_val)

        submit = (
            self.page.query_selector('#loginbtn') or
            self.page.query_selector('button[type="submit"]')
        )
        if submit:
            submit.click()

        self.page.wait_for_load_state("networkidle", timeout=30000)
        time.sleep(2)

        if "login" in self.page.url.lower():
            raise RuntimeError("Логин не прошёл — проверь UNI_LOGIN/UNI_PASSWORD")

        print("✅ Авторизация успешна")

    def goto(self, url: str):
        self.page.goto(url, timeout=60000)
        self.page.wait_for_load_state("networkidle")
        time.sleep(2)

    # ─── Поиск курсов ─────────────────────────────────────────

    def get_my_courses(self) -> list:
        """Собирает список курсов со всех страниц."""
        uni_url = os.getenv("UNI_URL", "https://campus.fa.ru")
        base = uni_url.split("/login")[0].rstrip("/")

        all_courses = {}
        urls_to_scan = [
            f"{base}/my/courses.php",
            f"{base}/my/",
            f"{base}/",
        ]

        for url in urls_to_scan:
            try:
                self.page.goto(url, timeout=60000)
                self.page.wait_for_load_state("networkidle")
                time.sleep(3)

                for el in self.page.query_selector_all('a[href*="/course/view.php"]'):
                    href = el.get_attribute("href") or ""
                    if "/course/view.php" not in href:
                        continue
                    name = el.inner_text().strip()
                    if not name:
                        name = (el.get_attribute("title") or
                                el.get_attribute("aria-label") or "").strip()
                    if href and name and href not in all_courses:
                        all_courses[href] = {"name": name, "url": href}
            except Exception as e:
                print(f"   ⚠️ Ошибка сканирования {url}: {e}")

        return list(all_courses.values())

    def get_course_info(self) -> dict:
        """
        Читает страницу курса (нужно предварительно сделать goto).
        Возвращает:
            name — настоящее название из title страницы
            description — описание/требования преподавателя
            teacher_name — ФИО преподавателя
            teacher_email — email преподавателя
            external_links — ссылки на внешние платформы
        """
        info = {
            "name": "",
            "description": "",
            "teacher_name": "",
            "teacher_email": "",
            "external_links": [],
        }

        # 1. Настоящее название курса из title
        try:
            title = self.page.title()
            # "Курс: <название>" или "Курс: <название>, Тема: ..."
            m = re.match(r"Курс:\s*(.+?)(?:,\s*Тема:|$)", title)
            if m:
                info["name"] = m.group(1).strip()
            else:
                info["name"] = title.strip()
        except Exception:
            pass

        # 2. Описание из #region-main (удаляем навигацию)
        try:
            description = self.page.evaluate("""() => {
                const main = document.querySelector('#region-main, [role="main"]');
                if (!main) return '';
                const clone = main.cloneNode(true);
                // Удаляем меню навигации и ссылки на другие секции
                clone.querySelectorAll('nav, .secondary-navigation, .breadcrumb, script, style').forEach(el => el.remove());
                return clone.innerText.trim();
            }""")
            info["description"] = description[:6000] if description else ""
        except Exception:
            pass

        # 3. ФИО преподавателя и email из описания
        if info["description"]:
            # Email — простой regex
            email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", info["description"])
            if email_match:
                info["teacher_email"] = email_match.group(0)

            # ФИО: ищем после "Информация о преподавателе"
            teacher_match = re.search(
                r"[Ии]нформаци[яи]\s+о\s+преподавателе[:\s]+([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?)",
                info["description"]
            )
            if teacher_match:
                info["teacher_name"] = teacher_match.group(1).strip()

        # 4. Внешние ссылки (на другие платформы)
        try:
            for a in self.page.query_selector_all("a[href]"):
                href = a.get_attribute("href") or ""
                for domain in EXTERNAL_DOMAINS:
                    if domain in href and href not in info["external_links"]:
                        info["external_links"].append(href)
        except Exception:
            pass

        return info

    def get_course_activities(self) -> list:
        """Сканирует страницу курса — собирает тесты, задания, видео."""
        activities = []
        seen = set()
        time.sleep(2)

        # Раскрываем свёрнутые секции
        try:
            for c in self.page.query_selector_all('[aria-expanded="false"]')[:20]:
                try:
                    c.click()
                    time.sleep(0.2)
                except Exception:
                    pass
        except Exception:
            pass

        selectors = [
            '.activityinstance a',
            '.activity a.aalink',
            'li.activity a[href*="/mod/"]',
        ]

        for selector in selectors:
            for el in self.page.query_selector_all(selector):
                href = el.get_attribute("href") or ""
                if not href or href in seen or "/mod/" not in href:
                    continue
                name = el.inner_text().strip() or "Без названия"

                if "/mod/quiz/" in href:
                    atype = "quiz"
                elif "/mod/assign/" in href:
                    atype = "assignment"
                elif "/mod/url/" in href or "mts-link" in href or "webinar.ru" in href:
                    atype = "video"
                elif "/mod/resource/" in href:
                    atype = "pdf"
                elif "/mod/lesson/" in href:
                    atype = "lesson"
                else:
                    atype = "other"

                activities.append({"type": atype, "name": name, "url": href})
                seen.add(href)

        # Прямые ссылки на эфиры
        for el in self.page.query_selector_all('a[href*="mts-link.ru"], a[href*="webinar.ru"]'):
            href = el.get_attribute("href") or ""
            if href and href not in seen:
                activities.append({"type": "video", "name": el.inner_text().strip() or "Эфир", "url": href})
                seen.add(href)

        return activities

    # ─── Состояние теста ──────────────────────────────────────

    def get_quiz_state(self) -> dict:
        """
        Определяет состояние теста на странице превью.
        Возвращает:
            state: "new" | "in_progress" | "done"
            max_attempts: int (0 = неограниченно)
            grade: строка с оценкой если done
        """
        state_info = self.page.evaluate("""() => {
            const buttons = [...document.querySelectorAll('button, input[type="submit"], a.btn')]
                .map(b => (b.innerText || b.value || '').trim()).filter(t => t);
            
            // Есть ли оценка?
            let gradeText = '';
            const gradeEl = document.querySelector('.generaltable') || document.querySelector('[class*="summary"]');
            if (gradeEl) {
                const txt = gradeEl.innerText;
                const m = txt.match(/итогова[яй]\\s+оценк[аи][^\\d]+([\\d.,/]+)/i);
                if (m) gradeText = m[1];
            }
            
            // Количество попыток (например "Разрешено попыток: 3")
            let maxAttempts = 0;
            const pageText = document.body.innerText;
            const attemptMatch = pageText.match(/[Рр]азрешено\\s+попыт[а-я]+:\\s*(\\d+)/);
            if (attemptMatch) maxAttempts = parseInt(attemptMatch[1]);
            
            return { buttons, gradeText, maxAttempts };
        }""")

        buttons = state_info.get("buttons", [])
        has_continue = any("продолжить" in b.lower() for b in buttons)
        has_start = any("начать тестирование" in b.lower() for b in buttons)
        has_grade = bool(state_info.get("gradeText"))

        if has_continue:
            state = "in_progress"
        elif has_grade and not has_start:
            state = "done"
        elif has_start:
            state = "new"
        else:
            state = "unknown"

        return {
            "state": state,
            "max_attempts": state_info.get("maxAttempts", 0),
            "grade": state_info.get("gradeText", ""),
        }

    def start_quiz(self, force: bool = False) -> bool:
        """
        Начинает тест: "Продолжить попытку" или "Начать тестирование".
        Возвращает True если удалось открыть вопросы.
        """
        # Продолжить текущую попытку
        btn = self.page.query_selector('button:has-text("Продолжить текущую попытку")') or \
              self.page.query_selector('a:has-text("Продолжить текущую попытку")')
        if btn:
            btn.click()
            self.page.wait_for_load_state("networkidle")
            time.sleep(2)
            print("✅ Продолжаю попытку")
            return True

        # Начать тестирование
        btn = self.page.query_selector('button:has-text("Начать тестирование")') or \
              self.page.query_selector('a:has-text("Начать тестирование")') or \
              self.page.query_selector('input[value="Начать тестирование"]')
        if btn:
            btn.click()
            self.page.wait_for_load_state("networkidle")
            time.sleep(2)
            # Подтверждение "Начать попытку"
            confirm = self.page.query_selector('button:has-text("Начать попытку"), input[value="Начать попытку"]')
            if confirm:
                confirm.click()
                self.page.wait_for_load_state("networkidle")
                time.sleep(2)
            print("✅ Начал тестирование")
            return True

        return False

    # ─── Вопросы теста ────────────────────────────────────────

    def get_quiz_data(self) -> list:
        """Извлекает вопросы всех поддерживаемых типов."""
        questions = []
        for block in self.page.query_selector_all(".que"):
            q_el = block.query_selector(".qtext")
            if not q_el:
                continue
            question_text = q_el.inner_text().strip()

            # Определяем тип по классу вопроса
            cls = block.get_attribute("class") or ""

            radios = block.query_selector_all('.answer input[type="radio"]')
            checkboxes = block.query_selector_all('.answer input[type="checkbox"]')
            text_inputs = block.query_selector_all('.answer input[type="text"]')
            textareas = block.query_selector_all('textarea')

            if "shortanswer" in cls or text_inputs:
                # Короткий текстовый ответ
                input_el = text_inputs[0] if text_inputs else block.query_selector('input[type="text"]')
                if input_el:
                    questions.append({
                        "question": question_text,
                        "type": "shortanswer",
                        "options": [],
                        "element": input_el,
                    })
            elif radios:
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
            elif textareas:
                questions.append({
                    "question": question_text, "type": "essay",
                    "options": [], "element": textareas[0]
                })

        print(f"  📋 Вопросов: {len(questions)}")
        return questions

    def fill_answer(self, question: dict, answer):
        """
        Универсальный метод ввода ответа.
        answer: int (индекс) для radio/checkbox, str для shortanswer/essay.
        """
        qtype = question.get("type")
        try:
            if qtype in ("radio", "checkbox"):
                elements = question.get("elements", [])
                if elements and 0 <= answer < len(elements):
                    elements[answer].click()
            elif qtype in ("shortanswer", "essay"):
                element = question.get("element")
                if element:
                    element.fill(str(answer))
            time.sleep(0.3)
        except Exception as e:
            print(f"  ⚠️ Не смог ввести ответ: {e}")

    def submit_quiz(self):
        """Завершает тест."""
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

    def get_quiz_grade(self) -> str:
        """Читает оценку со страницы результатов после сдачи теста."""
        try:
            time.sleep(3)
            grade = self.page.evaluate("""() => {
                const text = document.body.innerText;
                // "Оценка: 8,00 из 10,00" или "8.00/10.00"
                let m = text.match(/[Оо]ценк[аи][^:\\d\\n]{0,30}([\\d]+[,.]\\d+\\s*из\\s*[\\d]+[,.]\\d+)/i);
                if (m) return m[1].trim();
                // "Итоговая оценка: 80%"
                m = text.match(/[Ии]тогова[яй]\\s+оценк[аи][^:\\d\\n]{0,10}([\\d]+[,.]?\\d*\\s*%?)/i);
                if (m) return m[1].trim();
                // Таблица с Grade/Оценка
                const cells = [...document.querySelectorAll('td')];
                for (let i = 0; i < cells.length - 1; i++) {
                    const label = cells[i].innerText.trim().toLowerCase();
                    if (label.includes('оценка') || label.includes('grade')) {
                        const val = cells[i+1].innerText.trim();
                        if (val && /[\\d]/.test(val)) return val;
                    }
                }
                return '';
            }""")
            return grade or ""
        except Exception:
            return ""

    # ─── Задания ──────────────────────────────────────────────

    def get_assignment_info(self) -> dict:
        """
        Читает страницу задания.
        Возвращает текст требований, статус, дедлайн.
        """
        info = {"task_text": "", "status": "unknown", "deadline": ""}

        # Текст задания (intro)
        task_el = (
            self.page.query_selector(".box.generalbox") or
            self.page.query_selector("#intro") or
            self.page.query_selector('[role="main"]')
        )
        if task_el:
            info["task_text"] = task_el.inner_text().strip()

        # Статус из таблицы "Состояние ответа"
        try:
            status_info = self.page.evaluate("""() => {
                const table = document.querySelector('.submissionstatustable, .generaltable');
                if (!table) return {};
                const text = table.innerText;
                const status = text.match(/Состояние[^:]*:\\s*([^\\n]+)/i);
                const deadline = text.match(/Срок\\s+сдачи[^:]*:\\s*([^\\n]+)/i);
                return {
                    status: status ? status[1].trim() : '',
                    deadline: deadline ? deadline[1].trim() : '',
                };
            }""")
            if status_info.get("status"):
                txt = status_info["status"].lower()
                if "отправлено" in txt or "отправлен для оценивания" in txt:
                    info["status"] = "submitted"
                elif "оцен" in txt:
                    info["status"] = "graded"
                else:
                    info["status"] = "new"
            if status_info.get("deadline"):
                info["deadline"] = status_info["deadline"]
        except Exception:
            pass

        return info

    def open_assignment_editor(self):
        btn = (
            self.page.query_selector('button:has-text("Добавить ответ")') or
            self.page.query_selector('a:has-text("Добавить ответ")') or
            self.page.query_selector('button:has-text("Редактировать ответ")') or
            self.page.query_selector('a:has-text("Редактировать ответ")')
        )
        if btn:
            btn.click()
            self.page.wait_for_load_state("networkidle")
            time.sleep(2)
            return True
        return False

    def fill_text_answer(self, text: str):
        iframe = self.page.query_selector('iframe[id*="editor"], iframe.cke_wysiwyg_frame')
        if iframe:
            frame = iframe.content_frame()
            if frame:
                body = frame.query_selector("body")
                if body:
                    body.fill(text)
                    return

        textarea = self.page.query_selector("textarea")
        if textarea:
            textarea.fill(text)
            return

        editable = self.page.query_selector('[contenteditable="true"]')
        if editable:
            editable.click()
            editable.fill(text)

    def submit_assignment(self):
        btn = (
            self.page.query_selector('input[value="Сохранить изменения"]') or
            self.page.query_selector('button:has-text("Сохранить")') or
            self.page.query_selector('button[type="submit"]')
        )
        if btn:
            btn.click()
            self.page.wait_for_load_state("networkidle")

    # ─── Дедлайны из календаря ───────────────────────────────

    def get_upcoming_deadlines(self) -> list:
        """Читает календарь и возвращает предстоящие дедлайны."""
        uni_url = os.getenv("UNI_URL", "https://campus.fa.ru")
        base = uni_url.split("/login")[0].rstrip("/")

        try:
            self.page.goto(f"{base}/calendar/view.php?view=upcoming", timeout=60000)
            self.page.wait_for_load_state("networkidle")
            time.sleep(2)
        except Exception:
            return []

        deadlines = []
        try:
            items = self.page.query_selector_all('.event, [data-region="event-item"]')
            for item in items[:30]:
                text = item.inner_text().strip()
                if text:
                    # Пробуем найти ссылку на событие
                    link_el = item.query_selector("a")
                    url = link_el.get_attribute("href") if link_el else ""
                    deadlines.append({"text": text, "url": url or ""})
        except Exception:
            pass

        return deadlines

    def close(self):
        try:
            self.context.close()
            self.browser.close()
            self.playwright.stop()
        except Exception:
            pass
