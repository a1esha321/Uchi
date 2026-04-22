"""
debug_tool.py — инструмент для отладки и обучения навигации на сайте.

Функции:
- Заходит на любую страницу сайта
- Делает скриншот и отправляет в Telegram
- Присылает краткую структуру HTML (заголовки, ссылки, формы)
- Позволяет пошагово обучать бота
"""

import os
import time
import requests
from browser import UniBrowser


def _send_photo(photo_path: str, caption: str = ""):
    """Отправляет фото в Telegram."""
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    try:
        with open(photo_path, "rb") as f:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data={"chat_id": chat_id, "caption": caption[:1024], "parse_mode": "HTML"},
                files={"photo": f},
                timeout=30
            )
    except Exception as e:
        print(f"Ошибка отправки фото: {e}")


def _send_message(text: str):
    """Отправляет текст в Telegram."""
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text[:4096], "parse_mode": "HTML"},
            timeout=15
        )
    except Exception:
        pass


def debug_page(url: str):
    """
    Заходит на страницу и отправляет в Telegram:
    1. Скриншот (что видит бот)
    2. URL после перехода (вдруг редирект)
    3. Структуру: заголовки, кнопки, формы, ссылки
    4. HTML фрагмент главной области
    """
    _send_message(f"🔍 Исследую страницу: <code>{url}</code>")

    bot = UniBrowser(headless=True)
    try:
        bot.login()
        bot.page.goto(url, timeout=60000)
        bot.page.wait_for_load_state("networkidle")
        time.sleep(3)

        current_url = bot.page.url
        title = bot.page.title()

        # 1. Скриншот
        screenshot_path = "/tmp/debug_page.png"
        bot.page.screenshot(path=screenshot_path, full_page=False)
        _send_photo(screenshot_path, f"📸 <b>{title}</b>\n<code>{current_url}</code>")

        # 2. Структура страницы
        info = _analyze_page(bot.page)

        msg = f"<b>📊 Структура страницы</b>\n\n"
        msg += f"<b>Заголовок:</b> {title}\n"
        msg += f"<b>URL:</b> <code>{current_url}</code>\n\n"

        if info["headings"]:
            msg += f"<b>Заголовки ({len(info['headings'])}):</b>\n"
            for h in info["headings"][:10]:
                msg += f"  • {h}\n"
            msg += "\n"

        if info["buttons"]:
            msg += f"<b>Кнопки ({len(info['buttons'])}):</b>\n"
            for b in info["buttons"][:10]:
                msg += f"  • {b}\n"
            msg += "\n"

        if info["forms"]:
            msg += f"<b>Формы ввода ({len(info['forms'])}):</b>\n"
            for f in info["forms"][:5]:
                msg += f"  • {f}\n"
            msg += "\n"

        _send_message(msg)

        # 3. Ссылки по группам
        if info["links"]:
            links_msg = f"<b>🔗 Ссылки на странице ({len(info['links'])})</b>\n\n"
            for category, items in info["links_grouped"].items():
                if items:
                    links_msg += f"<b>{category}:</b>\n"
                    for item in items[:5]:
                        links_msg += f"  • {item['text'][:50]} → <code>{item['url'][:60]}</code>\n"
                    links_msg += "\n"
            _send_message(links_msg)

        # 4. Фрагмент HTML главной области
        main_html = bot.page.evaluate("""() => {
            const main = document.querySelector('main, [role="main"], #region-main, .main-content, body');
            return main ? main.outerHTML.substring(0, 3000) : '';
        }""")

        if main_html:
            _send_message(f"<b>💻 HTML главной области (первые 3000 символов):</b>\n<pre>{_escape_html(main_html[:2000])}</pre>")

    except Exception as e:
        _send_message(f"❌ Ошибка: <code>{str(e)[:500]}</code>")
    finally:
        bot.close()


def _analyze_page(page) -> dict:
    """Анализирует страницу и возвращает её структуру."""
    result = {
        "headings": [],
        "buttons": [],
        "forms": [],
        "links": [],
        "links_grouped": {},
    }

    # Заголовки h1-h3
    for h in page.query_selector_all("h1, h2, h3"):
        text = h.inner_text().strip()
        if text:
            result["headings"].append(text[:80])

    # Кнопки
    for b in page.query_selector_all('button, input[type="submit"], input[type="button"]'):
        text = (b.inner_text() or b.get_attribute("value") or "").strip()
        if text:
            result["buttons"].append(text[:60])

    # Поля форм
    for inp in page.query_selector_all('input[type="text"], input[type="password"], textarea, select'):
        name = inp.get_attribute("name") or inp.get_attribute("id") or "без имени"
        placeholder = inp.get_attribute("placeholder") or ""
        inp_type = inp.get_attribute("type") or inp.evaluate("el => el.tagName")
        info = f"{name} ({inp_type})"
        if placeholder:
            info += f" — {placeholder[:30]}"
        result["forms"].append(info)

    # Ссылки — группируем по типу
    grouped = {
        "Тесты (/mod/quiz)": [],
        "Задания (/mod/assign)": [],
        "Курсы (/course)": [],
        "Видео/МТС (мts-link)": [],
        "Личный кабинет (/my)": [],
        "Другие": [],
    }

    for a in page.query_selector_all("a[href]"):
        href = a.get_attribute("href") or ""
        text = a.inner_text().strip() or a.get_attribute("title") or ""
        if not href or href.startswith("#") or href.startswith("javascript"):
            continue

        link_info = {"text": text[:60], "url": href}
        result["links"].append(link_info)

        # Категоризация
        if "/mod/quiz/" in href:
            grouped["Тесты (/mod/quiz)"].append(link_info)
        elif "/mod/assign/" in href:
            grouped["Задания (/mod/assign)"].append(link_info)
        elif "/course/view" in href:
            grouped["Курсы (/course)"].append(link_info)
        elif "mts-link" in href or "webinar.ru" in href:
            grouped["Видео/МТС (мts-link)"].append(link_info)
        elif "/my/" in href:
            grouped["Личный кабинет (/my)"].append(link_info)
        else:
            grouped["Другие"].append(link_info)

    result["links_grouped"] = grouped
    return result


def debug_test_page(url: str):
    """
    Специализированная отладка страницы теста.
    Отправляет в Telegram всю информацию о вопросах: HTML, классы, структуру.
    """
    _send_message(f"🧪 Отладка теста: <code>{url}</code>")

    bot = UniBrowser(headless=True)
    try:
        bot.login()
        bot.page.goto(url, timeout=60000)
        bot.page.wait_for_load_state("networkidle")
        time.sleep(3)

        # Попытаться начать тест
        if bot.start_quiz():
            time.sleep(2)

        # Скриншот
        screenshot_path = "/tmp/debug_test.png"
        bot.page.screenshot(path=screenshot_path, full_page=True)
        _send_photo(screenshot_path, "📸 Страница теста")

        # Анализируем структуру вопросов
        analysis = bot.page.evaluate("""() => {
            // Ищем все возможные контейнеры вопросов
            const selectors = ['.que', '.question', '[class*="question"]', '.quiz-question', 'fieldset'];
            let results = [];
            
            for (const sel of selectors) {
                const elements = document.querySelectorAll(sel);
                if (elements.length > 0) {
                    results.push(`${sel}: ${elements.length} элементов`);
                    // Берём первый элемент и анализируем его структуру
                    const first = elements[0];
                    const classes = first.className;
                    const inputs = first.querySelectorAll('input');
                    const labels = first.querySelectorAll('label');
                    
                    results.push(`  Классы: ${classes}`);
                    results.push(`  Inputs: ${inputs.length}`);
                    results.push(`  Labels: ${labels.length}`);
                    
                    // HTML первого вопроса
                    if (first.outerHTML) {
                        results.push(`  HTML (500 симв): ${first.outerHTML.substring(0, 500)}`);
                    }
                    break;
                }
            }
            
            if (results.length === 0) {
                results.push('Контейнеры вопросов не найдены');
                // Показываем что есть на странице
                results.push(`Total inputs: ${document.querySelectorAll('input').length}`);
                results.push(`Total labels: ${document.querySelectorAll('label').length}`);
                results.push(`Total fieldsets: ${document.querySelectorAll('fieldset').length}`);
            }
            
            return results.join('\\n');
        }""")

        _send_message(f"<b>🔍 Анализ структуры теста:</b>\n<pre>{_escape_html(analysis)}</pre>")

        # Пробуем извлечь текст первого вопроса любым способом
        first_question_html = bot.page.evaluate("""() => {
            const q = document.querySelector('.que, .question, [class*="question"], fieldset');
            return q ? q.outerHTML.substring(0, 2000) : 'Вопрос не найден';
        }""")

        _send_message(f"<b>📝 HTML первого вопроса:</b>\n<pre>{_escape_html(first_question_html[:2000])}</pre>")

    except Exception as e:
        _send_message(f"❌ Ошибка: <code>{str(e)[:500]}</code>")
    finally:
        bot.close()


def _escape_html(text: str) -> str:
    """Экранирует HTML для отправки в Telegram."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))
