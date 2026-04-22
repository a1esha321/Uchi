"""
telegram_notifier.py — отправляет сообщения в Telegram и ждёт подтверждения 
через inline-кнопки (approve/skip).
"""

import requests
import time
import os
from dotenv import load_dotenv

load_dotenv()


def _get_base():
    """Возвращает BASE URL Telegram API — лениво, чтобы переменные успели загрузиться."""
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_TOKEN не задан в переменных окружения")
    return f"https://api.telegram.org/bot{token}"


def _get_chat_id():
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        raise ValueError("TELEGRAM_CHAT_ID не задан в переменных окружения")
    return chat_id


class TelegramNotifier:
    """Уведомления и подтверждения через Telegram."""

    def send(self, text: str, keyboard=None) -> int:
        """Отправляет сообщение. Возвращает message_id или None."""
        try:
            base = _get_base()
            chat_id = _get_chat_id()
        except ValueError as e:
            print(f"Telegram не настроен: {e}")
            return None

        payload = {
            "chat_id": chat_id,
            "text": text[:4096],
            "parse_mode": "HTML",
        }
        if keyboard:
            payload["reply_markup"] = {"inline_keyboard": keyboard}

        try:
            r = requests.post(f"{base}/sendMessage", json=payload, timeout=15)
            data = r.json()
            if data.get("ok"):
                return data["result"]["message_id"]
            print(f"Telegram ошибка: {data}")
        except Exception as e:
            print(f"Telegram недоступен: {e}")
        return None

    def edit(self, message_id: int, text: str):
        """Редактирует существующее сообщение."""
        if not message_id:
            return
        try:
            base = _get_base()
            chat_id = _get_chat_id()
            requests.post(f"{base}/editMessageText", json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text[:4096],
                "parse_mode": "HTML",
            }, timeout=15)
        except Exception:
            pass

    def _answer_callback(self, callback_id: str):
        try:
            base = _get_base()
            requests.post(
                f"{base}/answerCallbackQuery",
                json={"callback_query_id": callback_id},
                timeout=5
            )
        except Exception:
            pass

    def wait_for_callback(self, allowed_data: list, timeout: int = 600) -> str:
        """
        Ждёт нажатия кнопки в Telegram.
        ВНИМАНИЕ: не использовать параллельно с основным polling бота!
        Этот метод вызывается только из потока агента, когда основной бот уже
        получил сообщение и передал управление.
        """
        try:
            base = _get_base()
        except ValueError:
            return None

        offset = None
        deadline = time.time() + timeout

        while time.time() < deadline:
            params = {"timeout": 20}
            if offset:
                params["offset"] = offset
            try:
                r = requests.get(f"{base}/getUpdates", params=params, timeout=25)
                updates = r.json().get("result", [])
            except Exception:
                time.sleep(5)
                continue

            for update in updates:
                offset = update["update_id"] + 1
                cb = update.get("callback_query")
                if cb and cb.get("data") in allowed_data:
                    self._answer_callback(cb["id"])
                    return cb["data"]

        return None

    def confirm_quiz(self, subject_name: str, questions: list,
                     answers: list, confidences: list) -> str:
        """Отправляет тест на подтверждение. Возвращает 'approve', 'skip' или None."""
        lines = [f"<b>📝 Тест: {subject_name}</b>\n"]

        for i, (q, ans_idx, conf) in enumerate(zip(questions, answers, confidences)):
            conf_pct = int(conf * 100)
            emoji = "🟢" if conf_pct >= 80 else "🟡" if conf_pct >= 50 else "🔴"
            q_short = q["question"][:100] + ("..." if len(q["question"]) > 100 else "")
            options = q.get("options", [])
            a_text = options[ans_idx] if options and ans_idx < len(options) else "—"
            a_short = a_text[:60] + ("..." if len(a_text) > 60 else "")
            lines.append(f"<b>В{i+1}.</b> {q_short}\n  → {a_short}\n  {emoji} {conf_pct}%\n")

        avg = int(sum(confidences) / len(confidences) * 100) if confidences else 0
        lines.append(f"\nСредняя уверенность: <b>{avg}%</b>")

        text = "\n".join(lines)
        keyboard = [[
            {"text": "✅ Отправить", "callback_data": "approve"},
            {"text": "❌ Пропустить", "callback_data": "skip"},
        ]]

        msg_id = self.send(text, keyboard)
        if not msg_id:
            return None

        print("⏳ Жду подтверждения в Telegram...")
        result = self.wait_for_callback(["approve", "skip"], timeout=600)

        suffix = {
            "approve": "\n\n<b>✅ Подтверждено — отправляю</b>",
            "skip": "\n\n<b>❌ Пропущено</b>",
            None: "\n\n<b>⌛ Таймаут — пропускаю</b>"
        }.get(result, "")

        self.edit(msg_id, text + suffix)
        return result

    def confirm_assignment(self, subject_name: str, task_text: str,
                           answer: str, confidence: float = 0.7) -> str:
        """Отправляет черновик задания на подтверждение."""
        conf_pct = int(confidence * 100)
        emoji = "🟢" if conf_pct >= 80 else "🟡" if conf_pct >= 50 else "🔴"

        text = (
            f"<b>✍️ Задание: {subject_name}</b>\n\n"
            f"<b>Требования:</b>\n{task_text[:300]}{'...' if len(task_text) > 300 else ''}\n\n"
            f"<b>Черновик:</b>\n{answer[:800]}{'...' if len(answer) > 800 else ''}\n\n"
            f"{emoji} Уверенность: <b>{conf_pct}%</b>"
        )

        keyboard = [[
            {"text": "✅ Отправить", "callback_data": "approve"},
            {"text": "❌ Пропустить", "callback_data": "skip"},
        ]]

        msg_id = self.send(text, keyboard)
        if not msg_id:
            return None

        print("⏳ Жду подтверждения в Telegram...")
        result = self.wait_for_callback(["approve", "skip"], timeout=600)

        suffix = {
            "approve": "\n\n<b>✅ Подтверждено — отправляю</b>",
            "skip": "\n\n<b>❌ Пропущено</b>",
            None: "\n\n<b>⌛ Таймаут — пропускаю</b>"
        }.get(result, "")

        self.edit(msg_id, text + suffix)
        return result

    def notify(self, text: str):
        self.send(text)

    def notify_lecture_done(self, subject_name: str, words: int):
        self.send(f"🎓 Лекция завершена: <b>{subject_name}</b>\nКонспект: {words} слов")

    def notify_error(self, subject_name: str, error: str):
        self.send(f"❌ Ошибка: <b>{subject_name}</b>\n<code>{error[:300]}</code>")
