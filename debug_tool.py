"""
debug_tool.py — инструмент отладки навигации.
"""

import os
import time
import json
import requests
from browser import UniBrowser


def _send_photo(path: str, caption: str = ""):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    try:
        with open(path, "rb") as f:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data={"chat_id": chat_id, "caption": caption[:1024], "parse_mode": "HTML"},
                files={"photo": f}, timeout=30
            )
    except Exception as e:
        print(f"Фото: {e}")


def _send(text: str):
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


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def debug_page(url: str):
    """Исследует страницу — скриншот + текст + структура."""
    _send(f"🔍 <code>{url}</code>")

    bot = UniBrowser(headless=True)
    try:
        bot.login()
        bot.page.goto(url, timeout=60000)
        bot.page.wait_for_load_state("networkidle")
        time.sleep(3)

        title = bot.page.title()
        path = "/tmp/debug.png"
        bot.page.screenshot(path=path)
        _send_photo(path, f"📸 {title[:200]}")

        # Текст главной области
        main_text = bot.page.evaluate("""() => {
            const main = document.querySelector('#region-main, [role="main"], .course-content, main');
            if (!main) return '';
            const clone = main.cloneNode(true);
            clone.querySelectorAll('script, style, nav, header, footer').forEach(el => el.remove());
            return clone.innerText.trim();
        }""")

        if main_text:
            _send(f"<b>📄 Содержимое ({len(main_text)} симв):</b>\n<pre>{_esc(main_text[:3500])}</pre>")

    except Exception as e:
        _send(f"❌ <code>{str(e)[:500]}</code>")
    finally:
        bot.close()


def debug_test_page(url: str):
    """Отладка теста — скриншот вопросов + анализ."""
    _send(f"🧪 <code>{url}</code>")

    bot = UniBrowser(headless=True)
    try:
        bot.login()
        bot.page.goto(url, timeout=60000)
        bot.page.wait_for_load_state("networkidle")
        time.sleep(3)

        # Определяем состояние
        state = bot.get_quiz_state()
        _send(f"<b>📋 Состояние теста</b>\n"
              f"Статус: <code>{state['state']}</code>\n"
              f"Попыток разрешено: {state['max_attempts'] or '∞'}\n"
              f"Оценка: {state.get('grade') or '—'}")

        if state["state"] in ("new", "in_progress"):
            bot.start_quiz()

        path = "/tmp/debug_test.png"
        bot.page.screenshot(path=path, full_page=True)
        _send_photo(path, "📸 Страница теста")

        analysis = bot.page.evaluate("""() => {
            const questions = document.querySelectorAll('.que');
            if (questions.length === 0) return 'Вопросы не найдены';
            const first = questions[0];
            const type = first.className.match(/que\\s+(\\w+)/);
            const qtext = first.querySelector('.qtext');
            return {
                total: questions.length,
                type: type ? type[1] : 'unknown',
                question: qtext ? qtext.innerText.trim().substring(0, 300) : '',
                inputs: {
                    radios: first.querySelectorAll('input[type="radio"]').length,
                    checkboxes: first.querySelectorAll('input[type="checkbox"]').length,
                    textInputs: first.querySelectorAll('input[type="text"]').length,
                    textareas: first.querySelectorAll('textarea').length,
                },
            };
        }""")
        _send(f"<b>🔍 Анализ:</b>\n<pre>{_esc(json.dumps(analysis, ensure_ascii=False, indent=2))}</pre>")

    except Exception as e:
        _send(f"❌ <code>{str(e)[:500]}</code>")
    finally:
        bot.close()
