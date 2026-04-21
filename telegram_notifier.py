"""
telegram_notifier.py — отправляет тесты и задания тебе в Telegram
перед отправкой, ждёт подтверждения.

Как получить токен бота:
1. Напиши @BotFather в Telegram
2. /newbot → придумай имя → получи токен
3. Вставь токен и свой chat_id в .env

Как узнать свой chat_id:
1. Напиши своему боту любое сообщение
2. Открой: https://api.telegram.org/bot<TOKEN>/getUpdates
3. Найди "chat": {"id": XXXXXXX} — это твой chat_id
"""

import requests
import time
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


class TelegramNotifier:

    # ─── ОТПРАВКА СООБЩЕНИЙ ───────────────────────────────────

    def send(self, text: str, keyboard=None) -> int:
        """Отправляет сообщение, возвращает message_id"""
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }
        if keyboard:
            payload["reply_markup"] = {"inline_keyboard": keyboard}

        r = requests.post(f"{BASE}/sendMessage", json=payload, timeout=10)
        data = r.json()
        if data.get("ok"):
            return data["result"]["message_id"]
        else:
            print(f"⚠️ Telegram ошибка: {data}")
            return None

    def edit(self, message_id: int, text: str):
        """Редактирует существующее сообщение"""
        requests.post(f"{BASE}/editMessageText", json={
            "chat_id": TELEGRAM_CHAT_ID,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
        }, timeout=10)

    def answer_callback(self, callback_id: str):
        """Убирает "часики" на кнопке после нажатия"""
        requests.post(f"{BASE}/answerCallbackQuery", json={
            "callback_query_id": callback_id
        }, timeout=5)

    # ─── ОЖИДАНИЕ ОТВЕТА ──────────────────────────────────────

    def wait_for_callback(self, allowed_data: list[str], timeout: int = 300) -> str | None:
        """
        Ждёт нажатия кнопки в Telegram.
        allowed_data — список допустимых callback_data
        timeout — максимальное ожидание в секундах (по умолчанию 5 минут)
        Возвращает нажатый callback_data или None если истёк таймаут.
        """
        offset = None
        deadline = time.time() + timeout

        while time.time() < deadline:
            params = {"timeout": 30}
            if offset:
                params["offset"] = offset

            try:
                r = requests.get(f"{BASE}/getUpdates", params=params, timeout=35)
                updates = r.json().get("result", [])
            except Exception as e:
                print(f"⚠️ Ошибка polling: {e}")
                time.sleep(5)
                continue

            for update in updates:
                offset = update["update_id"] + 1
                cb = update.get("callback_query")
                if cb and cb["data"] in allowed_data:
                    self.answer_callback(cb["id"])
                    return cb["data"]

        return None  # таймаут

    # ─── ПОДТВЕРЖДЕНИЕ ТЕСТА ──────────────────────────────────

    def confirm_quiz(self, subject_name: str, questions: list[dict], answers: list[int], confidences: list[float]) -> str:
        """
        Отправляет тест в Telegram с ответами и уверенностью.
        Ждёт подтверждения от пользователя.

        Возвращает: "approve" | "skip" | None (таймаут)
        """
        # Формируем текст сообщения
        lines = [f"📝 <b>Тест: {subject_name}</b>\n"]

        for i, (q, ans_idx, conf) in enumerate(zip(questions, answers, confidences)):
            conf_pct = int(conf * 100)

            # Эмодзи по уверенности
            if conf_pct >= 80:
                conf_emoji = "🟢"
            elif conf_pct >= 50:
                conf_emoji = "🟡"
            else:
                conf_emoji = "🔴"

            question_short = q["question"][:120] + ("..." if len(q["question"]) > 120 else "")
            answer_text = q["options"][ans_idx] if q["options"] else "текстовый ответ"
            answer_short = answer_text[:80] + ("..." if len(answer_text) > 80 else "")

            lines.append(
                f"<b>В{i+1}.</b> {question_short}\n"
                f"  → {answer_short}\n"
                f"  {conf_emoji} Уверенность: {conf_pct}%\n"
            )

        # Считаем среднюю уверенность
        avg_conf = int(sum(confidences) / len(confidences) * 100) if confidences else 0
        lines.append(f"\n📊 Средняя уверенность: <b>{avg_conf}%</b>")
        lines.append(f"❓ Вопросов: {len(questions)}")

        text = "\n".join(lines)

        # Кнопки
        keyboard = [[
            {"text": "✅ Отправить", "callback_data": "approve"},
            {"text": "⏭ Пропустить", "callback_data": "skip"},
        ]]

        msg_id = self.send(text, keyboard)
        print(f"📱 Тест отправлен в Telegram, жду подтверждения...")

        result = self.wait_for_callback(["approve", "skip"], timeout=600)  # 10 минут

        if result == "approve":
            self.edit(msg_id, text + "\n\n<b>✅ Подтверждено — отправляю</b>")
        elif result == "skip":
            self.edit(msg_id, text + "\n\n<b>⏭ Пропущено</b>")
        else:
            self.edit(msg_id, text + "\n\n<b>⏰ Таймаут — пропускаю</b>")

        return result

    # ─── ПОДТВЕРЖДЕНИЕ ЗАДАНИЯ ────────────────────────────────

    def confirm_assignment(self, subject_name: str, task_text: str, answer: str, confidence: float) -> str:
        """
        Отправляет задание в Telegram с черновиком и уверенностью.
        Ждёт подтверждения.

        Возвращает: "approve" | "skip" | None (таймаут)
        """
        conf_pct = int(confidence * 100)
        if conf_pct >= 80:
            conf_emoji = "🟢"
        elif conf_pct >= 50:
            conf_emoji = "🟡"
        else:
            conf_emoji = "🔴"

        task_short = task_text[:200] + ("..." if len(task_text) > 200 else "")
        answer_short = answer[:600] + ("..." if len(answer) > 600 else "")

        text = (
            f"✍️ <b>Задание: {subject_name}</b>\n\n"
            f"<b>Задание:</b>\n{task_short}\n\n"
            f"<b>Черновик ответа:</b>\n{answer_short}\n\n"
            f"{conf_emoji} Уверенность: <b>{conf_pct}%</b>\n"
            f"📝 Слов в ответе: {len(answer.split())}"
        )

        keyboard = [[
            {"text": "✅ Отправить", "callback_data": "approve"},
            {"text": "⏭ Пропустить", "callback_data": "skip"},
        ]]

        msg_id = self.send(text, keyboard)
        print(f"📱 Задание отправлено в Telegram, жду подтверждения...")

        result = self.wait_for_callback(["approve", "skip"], timeout=600)

        if result == "approve":
            self.edit(msg_id, text + "\n\n<b>✅ Подтверждено — отправляю</b>")
        elif result == "skip":
            self.edit(msg_id, text + "\n\n<b>⏭ Пропущено</b>")
        else:
            self.edit(msg_id, text + "\n\n<b>⏰ Таймаут — пропускаю</b>")

        return result

    # ─── УВЕДОМЛЕНИЯ ──────────────────────────────────────────

    def notify(self, text: str):
        """Простое уведомление без кнопок"""
        self.send(text)

    def notify_lecture_done(self, subject_name: str, words: int, notes_file: str):
        self.send(
            f"🎓 <b>Лекция завершена</b>\n\n"
            f"Предмет: {subject_name}\n"
            f"Конспект: {words} слов\n"
            f"Файл: {notes_file}"
        )

    def notify_error(self, subject_name: str, error: str):
        self.send(
            f"❌ <b>Ошибка</b>\n\n"
            f"Предмет: {subject_name}\n"
            f"Ошибка: {error[:300]}"
        )
