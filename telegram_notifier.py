"""
telegram_notifier.py — отправка уведомлений и подтверждений в Telegram.
"""

import requests
import time
import os
from dotenv import load_dotenv

load_dotenv()


def _base():
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_TOKEN не задан")
    return f"https://api.telegram.org/bot{token}"


def _chat_id():
    c = os.getenv("TELEGRAM_CHAT_ID")
    if not c:
        raise ValueError("TELEGRAM_CHAT_ID не задан")
    return c


class TelegramNotifier:
    def send(self, text: str, keyboard=None) -> int:
        try:
            base = _base()
            chat_id = _chat_id()
        except ValueError as e:
            print(f"Telegram: {e}")
            return None

        payload = {"chat_id": chat_id, "text": text[:4096], "parse_mode": "HTML"}
        if keyboard:
            payload["reply_markup"] = {"inline_keyboard": keyboard}
        try:
            r = requests.post(f"{base}/sendMessage", json=payload, timeout=15)
            data = r.json()
            if data.get("ok"):
                return data["result"]["message_id"]
        except Exception as e:
            print(f"Telegram: {e}")
        return None

    def edit(self, message_id: int, text: str):
        if not message_id:
            return
        try:
            requests.post(f"{_base()}/editMessageText", json={
                "chat_id": _chat_id(),
                "message_id": message_id,
                "text": text[:4096],
                "parse_mode": "HTML",
            }, timeout=15)
        except Exception:
            pass

    def wait_for_callback(self, allowed_data: list, timeout: int = 600) -> str:
        """Подменяется в telegram_bot.py на центральную очередь."""
        return None

    def confirm_single_attempt_quiz(self, subject_name: str, quiz_name: str,
                                     max_attempts: int) -> str:
        """
        Отдельное подтверждение для тестов с одной попыткой.
        Возвращает 'start' или 'skip'.
        """
        text = (
            f"⚠️ <b>Тест с {max_attempts} попыткой!</b>\n\n"
            f"Предмет: <b>{subject_name}</b>\n"
            f"Тест: {quiz_name}\n\n"
            f"Бот НЕ будет запускать его сам — это контрольный.\n"
            f"Решай сам или нажми кнопку ниже чтобы разрешить боту."
        )
        keyboard = [[
            {"text": "🎯 Разрешить боту", "callback_data": "start"},
            {"text": "⏭ Пропустить", "callback_data": "skip"},
        ]]

        msg_id = self.send(text, keyboard)
        if not msg_id:
            return "skip"

        result = self.wait_for_callback(["start", "skip"], timeout=1800)
        suffix = {
            "start": "\n\n<b>✅ Запускаю...</b>",
            "skip": "\n\n<b>⏭ Пропущено</b>",
            None: "\n\n<b>⌛ Таймаут — пропускаю</b>"
        }.get(result, "")
        self.edit(msg_id, text + suffix)
        return result or "skip"

    def confirm_quiz(self, subject_name: str, questions: list,
                     answers: list, confidences: list) -> str:
        lines = [f"<b>📝 Тест: {subject_name}</b>\n"]

        for i, (q, ans, conf) in enumerate(zip(questions, answers, confidences)):
            conf_pct = int(conf * 100)
            emoji = "🟢" if conf_pct >= 80 else "🟡" if conf_pct >= 50 else "🔴"
            q_short = q["question"][:100] + ("..." if len(q["question"]) > 100 else "")

            if q.get("type") in ("shortanswer", "essay"):
                a_text = str(ans)
            else:
                options = q.get("options", [])
                a_text = options[ans] if options and isinstance(ans, int) and ans < len(options) else "—"

            a_short = a_text[:80] + ("..." if len(a_text) > 80 else "")
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

        result = self.wait_for_callback(["approve", "skip"], timeout=1200)
        suffix = {
            "approve": "\n\n<b>✅ Подтверждено</b>",
            "skip": "\n\n<b>❌ Пропущено</b>",
            None: "\n\n<b>⌛ Таймаут</b>"
        }.get(result, "")
        self.edit(msg_id, text + suffix)
        return result

    def confirm_assignment(self, subject_name: str, task_text: str,
                           answer: str, confidence: float = 0.7) -> str:
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

        result = self.wait_for_callback(["approve", "skip"], timeout=1200)
        suffix = {
            "approve": "\n\n<b>✅ Подтверждено</b>",
            "skip": "\n\n<b>❌ Пропущено</b>",
            None: "\n\n<b>⌛ Таймаут</b>"
        }.get(result, "")
        self.edit(msg_id, text + suffix)
        return result

    def notify(self, text: str):
        self.send(text)

    def notify_lecture_done(self, subject_name: str, words: int):
        self.send(f"🎓 Лекция: <b>{subject_name}</b>\n{words} слов")

    def notify_error(self, subject_name: str, error: str):
        self.send(f"❌ <b>{subject_name}</b>\n<code>{error[:300]}</code>")
