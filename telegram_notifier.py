"""
telegram_notifier.py — отправляет уведомления и ждёт подтверждения в Telegram.
"""

import requests
import time
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BASE = f"https://api.telegram.org/bot{TOKEN}"


class TelegramNotifier:

    def send(self, text: str, keyboard=None) -> int:
        """Отправляет сообщение. Возвращает message_id."""
        payload = {
            "chat_id": CHAT_ID,
            "text": text[:4096],
            "parse_mode": "HTML",
        }
        if keyboard:
            payload["reply_markup"] = {"inline_keyboard": keyboard}
        try:
            r = requests.post(f"{BASE}/sendMessage", json=payload, timeout=15)
            data = r.json()
            if data.get("ok"):
                return data["result"]["message_id"]
            print(f"Telegram ошибка: {data}")
        except Exception as e:
            print(f"Telegram недоступен: {e}")
        return None

    def edit(self, message_id: int, text: str):
        """Редактирует сообщение."""
        try:
            requests.post(f"{BASE}/editMessageText", json={
                "chat_id": CHAT_ID,
                "message_id": message_id,
                "text": text[:4096],
                "parse_mode": "HTML",
            }, timeout=15)
        except Exception as e:
            print(f"Ошибка редактирования: {e}")

    def answer_callback(self, callback_id: str):
        try:
            requests.post(f"{BASE}/answerCallbackQuery",
                          json={"callback_query_id": callback_id}, timeout=5)
        except Exception:
            pass

    def wait_for_callback(self, allowed_data: list, timeout: int = 600) -> str:
        """Ждёт нажатия кнопки в Telegram."""
        offset = None
        deadline = time.time() + timeout

        while time.time() < deadline:
            params = {"timeout": 20}
            if offset:
                params["offset"] = offset
            try:
                r = requests.get(f"{BASE}/getUpdates", params=params, timeout=25)
                updates = r.json().get("result", [])
            except Exception as e:
                print(f"Ошибка polling: {e}")
                time.sleep(5)
                continue

            for update in updates:
                offset = update["update_id"] + 1
                cb = update.get("callback_query")
                if cb and cb["data"] in allowed_data:
                    self.answer_callback(cb["id"])
                    return cb["data"]

        return None

    def confirm_quiz(self, subject_name: str, questions: list, answers: list, confidences: list) -> str:
        """Отправляет тест на подтверждение."""
        lines = [f"<b>Тест: {subject_name}</b>\n"]

        for i, (q, ans_idx, conf) in enumerate(zip(questions, answers, confidences)):
            conf_pct = int(conf * 100)
            emoji = "🟢" if conf_pct >= 80 else "🟡" if conf_pct >= 50 else "🔴"
            q_short = q["question"][:100] + ("..." if len(q["question"]) > 100 else "")
            a_text = q["options"][ans_idx] if q["options"] else "—"
            a_short = a_text[:60] + ("..." if len(a_text) > 60 else "")
            lines.append(f"<b>В{i+1}.</b> {q_short}\n  -> {a_short}\n  {emoji} {conf_pct}%\n")

        avg = int(sum(confidences) / len(confidences) * 100) if confidences else 0
        lines.append(f"\nСредняя уверенность: <b>{avg}%</b>")

        text = "\n".join(lines)
        keyboard = [[
            {"text": "Отправить", "callback_data": "approve"},
            {"text": "Пропустить", "callback_data": "skip"},
        ]]

        msg_id = self.send(text, keyboard)
        print(f"Тест отправлен в Telegram, жду подтверждения...")
        result = self.wait_for_callback(["approve", "skip"], timeout=600)

        suffix = {
            "approve": "\n\n<b>Подтверждено — отправляю</b>",
            "skip": "\n\n<b>Пропущено</b>",
            None: "\n\n<b>Таймаут — пропускаю</b>"
        }.get(result, "")

        if msg_id:
            self.edit(msg_id, text + suffix)
        return result

    def confirm_assignment(self, subject_name: str, task_text: str, answer: str, confidence: float) -> str:
        """Отправляет задание на подтверждение."""
        conf_pct = int(confidence * 100)
        emoji = "🟢" if conf_pct >= 80 else "🟡" if conf_pct >= 50 else "🔴"

        text = (
            f"<b>Задание: {subject_name}</b>\n\n"
            f"<b>Задание:</b>\n{task_text[:200]}...\n\n"
            f"<b>Черновик:</b>\n{answer[:500]}...\n\n"
            f"{emoji} Уверенность: <b>{conf_pct}%</b>"
        )

        keyboard = [[
            {"text": "Отправить", "callback_data": "approve"},
            {"text": "Пропустить", "callback_data": "skip"},
        ]]

        msg_id = self.send(text, keyboard)
        print(f"Задание отправлено в Telegram, жду подтверждения...")
        result = self.wait_for_callback(["approve", "skip"], timeout=600)

        suffix = {
            "approve": "\n\n<b>Подтверждено — отправляю</b>",
            "skip": "\n\n<b>Пропущено</b>",
            None: "\n\n<b>Таймаут — пропускаю</b>"
        }.get(result, "")

        if msg_id:
            self.edit(msg_id, text + suffix)
        return result

    def notify(self, text: str):
        self.send(text)

    def notify_lecture_done(self, subject_name: str, words: int, notes_file: str):
        self.send(f"Лекция завершена: <b>{subject_name}</b>\nКонспект: {words} слов")

    def notify_error(self, subject_name: str, error: str):
        self.send(f"Ошибка: <b>{subject_name}</b>\n{error[:300]}")
