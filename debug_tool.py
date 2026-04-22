"""
debug_tool.py — улучшенный инструмент отладки.
Показывает реальное содержимое страницы, а не шапку сайта.
"""

import os
import time
import requests
from browser import UniBrowser


def _send_photo(photo_path: str, caption: str = ""):
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
        print(f"Ошибка фото: {e}")


def _send_message(text: str):
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


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def debug_page(url: str):
    """Заходит на страницу и отправляет в Telegram её реальное содержимое."""
    _send_message(f"🔍 Исследую: <code>{url}</code>")

    bot = UniBrowser(headless=True)
    try:
        bot.login()
        bot.page.goto(url, timeout=60000)
        bot.page.wait_for_load_state("networkidle")
        time.sleep(3)

        current_url = bot.page.url
        title = bot.page.title()

        # Скриншот
        screenshot_path = "/tmp/debug_page.png"
        bot.page.screenshot(path=screenshot_path, full_page=False)
        _send_photo(screenshot_path, f"📸 {title[:150]}")

        # 1. Извлекаем ТЕКСТОВОЕ содержимое главной области
        main_text = bot.page.evaluate("""() => {
            const main = document.querySelector(
                '#region-main, [role="main"], .course-content, main, #page-content'
            );
            if (!main) return '';
            // Удаляем скрипты и стили из копии
            const clone = main.cloneNode(true);
            clone.querySelectorAll('script, style, nav, header, footer').forEach(el => el.remove());
            return clone.innerText.trim();
        }""")

        if main_text:
            _send_message(f"<b>📄 Содержимое страницы ({len(main_text)} симв):</b>\n<pre>{_escape_html(main_text[:3500])}</pre>")
        else:
            _send_message("⚠️ Не смог извлечь содержимое главной области")

        # 2. Смотрим именно секцию если URL с ?section=
        if "section=" in current_url or "#section-" in current_url:
            section_html = bot.page.evaluate("""() => {
                // Ищем содержимое текущей секции
                const section = document.querySelector(
                    '.section.main, li.section.current, .section-item'
                );
                if (!section) return '';
                const summary = section.querySelector('.summary, .content, .no-overflow');
                if (summary) return summary.innerText.trim();
                return section.innerText.trim().substring(0, 3000);
            }""")

            if section_html:
                _send_message(f"<b>📋 Текст секции:</b>\n<pre>{_escape_html(section_html[:3500])}</pre>")

        # 3. HTML конкретного блока (для понимания структуры)
        main_html = bot.page.evaluate("""() => {
            const main = document.querySelector(
                '#region-main .summary, .course-content .summary, .section .summary, #intro, .box.generalbox'
            );
            return main ? main.outerHTML.substring(0, 2500) : '';
        }""")

        if main_html:
            _send_message(f"<b>💻 HTML блока с описанием:</b>\n<pre>{_escape_html(main_html[:2500])}</pre>")

    except Exception as e:
        _send_message(f"❌ Ошибка: <code>{str(e)[:500]}</code>")
    finally:
        bot.close()


def debug_test_page(url: str):
    """Специализированная отладка страницы теста."""
    _send_message(f"🧪 Отладка теста: <code>{url}</code>")

    bot = UniBrowser(headless=True)
    try:
        bot.login()
        bot.page.goto(url, timeout=60000)
        bot.page.wait_for_load_state("networkidle")
        time.sleep(3)

        # Определяем состояние теста
        state_info = bot.page.evaluate("""() => {
            const info = {};
            
            // Кнопки на странице
            const buttons = [...document.querySelectorAll('button, input[type="submit"], a.btn')];
            info.buttons = buttons.map(b => (b.innerText || b.value || '').trim()).filter(t => t);
            
            // Есть ли оценка?
            const gradeEl = document.querySelector('.generaltable .c1, [class*="grade"]');
            info.hasGrade = !!gradeEl;
            
            // Количество вопросов на странице
            info.questions = document.querySelectorAll('.que').length;
            
            return info;
        }""")

        # Если тест ещё не начат — пытаемся начать
        if state_info["questions"] == 0:
            _send_message(
                f"<b>📋 Страница превью теста</b>\n"
                f"Кнопки: {', '.join(state_info['buttons'][:10])}\n\n"
                f"Пробую нажать 'Начать тестирование' или 'Продолжить попытку'..."
            )

            # Пробуем разные кнопки
            for btn_text in ["Продолжить текущую попытку", "Начать тестирование", "Начать новую попытку"]:
                btn = bot.page.query_selector(f'button:has-text("{btn_text}"), a:has-text("{btn_text}"), input[value="{btn_text}"]')
                if btn:
                    _send_message(f"✅ Нажимаю: {btn_text}")
                    btn.click()
                    bot.page.wait_for_load_state("networkidle")
                    time.sleep(2)
                    # Подтверждение "Начать попытку" если есть
                    confirm = bot.page.query_selector('button:has-text("Начать попытку"), input[value="Начать попытку"]')
                    if confirm:
                        confirm.click()
                        bot.page.wait_for_load_state("networkidle")
                        time.sleep(2)
                    break

        # Теперь делаем скриншот (возможно с вопросами)
        screenshot_path = "/tmp/debug_test.png"
        bot.page.screenshot(path=screenshot_path, full_page=True)
        _send_photo(screenshot_path, "📸 Страница теста")

        # Анализируем вопросы
        analysis = bot.page.evaluate("""() => {
            const questions = document.querySelectorAll('.que');
            if (questions.length === 0) return 'Вопросы не найдены';
            
            const first = questions[0];
            const type = first.className.match(/que\s+(\w+)/);
            const qtext = first.querySelector('.qtext');
            const qtextStr = qtext ? qtext.innerText.trim() : 'нет текста';
            
            // Типы input
            const radios = first.querySelectorAll('input[type="radio"]').length;
            const checkboxes = first.querySelectorAll('input[type="checkbox"]').length;
            const textInputs = first.querySelectorAll('input[type="text"]').length;
            const textareas = first.querySelectorAll('textarea').length;
            const selects = first.querySelectorAll('select').length;
            
            // Варианты ответов
            const labels = [...first.querySelectorAll('.answer label, .r0 label, .r1 label')];
            const options = labels.map(l => l.innerText.trim()).filter(t => t);
            
            return {
                total: questions.length,
                type: type ? type[1] : 'unknown',
                question: qtextStr.substring(0, 300),
                inputs: {radios, checkboxes, textInputs, textareas, selects},
                options: options.slice(0, 6)
            };
        }""")

        import json
        _send_message(f"<b>🔍 Анализ вопросов:</b>\n<pre>{_escape_html(json.dumps(analysis, ensure_ascii=False, indent=2))}</pre>")

    except Exception as e:
        _send_message(f"❌ Ошибка: <code>{str(e)[:500]}</code>")
    finally:
        bot.close()
