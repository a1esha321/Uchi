"""
course_requirements.py — полный парсер требований преподавателя.

Парсит все активности курса на campus.fa.ru / online.fa.ru,
структурирует по секциям и генерирует список задач для студента.
"""

import re
import logging
from typing import Optional

from groq import Groq

logger = logging.getLogger(__name__)
GROQ_MODEL = "llama-3.3-70b-versatile"

TASK_ICONS = {
    "quiz":       "🧪",
    "assignment": "✍️",
    "resource":   "📄",
    "folder":     "📁",
    "lesson":     "📖",
    "forum":      "💬",
    "page":       "📋",
    "url":        "🔗",
    "video":      "🎥",
    "scorm":      "📦",
    "label":      "•",
    "other":      "•",
}


class RequirementsParser:
    def __init__(self):
        self._groq: Optional[Groq] = None

    @property
    def groq(self) -> Groq:
        if self._groq is None:
            self._groq = Groq()
        return self._groq

    def parse(self, browser, course_url: str) -> dict:
        """
        Полный парсинг курса. browser должен быть залогинен.
        Возвращает dict с course_name, teacher_name, teacher_requirements,
        sections и task_list.
        """
        browser.goto(course_url)

        final_url = browser.page.url
        if "login" in final_url.lower():
            raise RuntimeError(
                f"Не удалось открыть курс — браузер попал на страницу логина.\n"
                f"URL: {final_url[:120]}\n"
                f"Проверь UNI_LOGIN / UNI_PASSWORD в Railway."
            )

        info = browser.get_course_info()
        sections = browser.get_course_structure()

        activity_count = sum(len(s.get("activities", [])) for s in sections)
        if activity_count == 0:
            raise RuntimeError(
                f"Курс открылся ({info.get('name', '?')}), но активностей не найдено.\n"
                f"Возможно, Moodle использует нестандартную вёрстку.\n"
                f"Используй /debug_course {course_url} для диагностики."
            )

        task_list = self._generate_task_list(
            info.get("name", ""),
            sections,
            info.get("description", ""),
        )

        return {
            "course_name": info.get("name", ""),
            "teacher_name": info.get("teacher_name", ""),
            "teacher_requirements": info.get("description", ""),
            "sections": sections,
            "task_list": task_list,
        }

    def _generate_task_list(self, course_name: str, sections: list,
                            teacher_req: str) -> str:
        lines = []
        for sec in sections:
            title = sec.get("title", "")
            acts = sec.get("activities", [])
            if not acts:
                continue
            if title:
                lines.append(f"[{title}]")
            for a in acts:
                mark = "✓" if a.get("completed") else "○"
                dl = f" | срок: {a['deadline']}" if a.get("deadline") else ""
                lines.append(f"  {mark} [{a['type'].upper()}] {a['name']}{dl}")
                if a.get("description"):
                    lines.append(f"     ↳ {a['description'][:120]}")

        activities_text = "\n".join(lines[:100])
        if not activities_text:
            return "⚠️ Активностей не найдено — список задач сгенерировать невозможно."

        req_text = teacher_req[:2500] if teacher_req else "Не указаны"

        prompt = (
            f"Предмет: «{course_name}»\n\n"
            f"Требования преподавателя:\n{req_text}\n\n"
            f"Активности курса (○ = не выполнено, ✓ = выполнено):\n{activities_text}\n\n"
            f"Составь для студента-заочника полный структурированный список задач.\n"
            f"Правила:\n"
            f"1. Сгруппируй по типу: тесты, задания, материалы для изучения, форумы\n"
            f"2. Отметь ✓ уже выполненные\n"
            f"3. Для каждой задачи: что делать и влияет ли на итоговую оценку\n"
            f"4. Укажи рекомендуемый порядок выполнения\n"
            f"5. Выдели дедлайны, если они есть\n"
            f"Формат: нумерованный список на русском, без вступления, максимум конкретики."
        )

        try:
            r = self.groq.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1200,
                temperature=0.3,
            )
            return r.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"RequirementsParser generate: {e}")
            return f"⚠️ Не удалось сгенерировать список задач: {e}"

    def format_html(self, result: dict) -> str:
        name = result.get("course_name", "")
        teacher = result.get("teacher_name", "")
        task_list = result.get("task_list", "")
        sections = result.get("sections", [])

        total = sum(len(s.get("activities", [])) for s in sections)
        done = sum(
            1 for s in sections
            for a in s.get("activities", [])
            if a.get("completed")
        )
        graded_types = {"quiz", "assignment"}
        graded = sum(
            1 for s in sections
            for a in s.get("activities", [])
            if a.get("type") in graded_types
        )

        header = f"📋 <b>Требования: {name}</b>"
        if teacher:
            header += f"\n👤 {teacher}"
        header += (
            f"\n📊 Активностей: <b>{total}</b> | "
            f"Выполнено: <b>{done}</b> | "
            f"Оцениваемых: <b>{graded}</b>\n"
        )

        lines = [header, "\n<b>📝 Список задач:</b>\n"]
        for line in task_list.split("\n"):
            stripped = line.strip()
            if not stripped:
                lines.append("")
                continue
            if re.match(r"^\d+\.", stripped):
                lines.append(f"\n{stripped}")
            elif stripped.startswith(("•", "-", "–", "✓", "○", "*")):
                lines.append(f"  {stripped}")
            elif re.match(r"^[А-ЯЁA-Z][А-ЯЁA-Z\s]+:?$", stripped) or stripped.endswith(":"):
                lines.append(f"\n<b>{stripped}</b>")
            else:
                lines.append(stripped)

        return "\n".join(lines).strip()

    def format_sections_html(self, sections: list) -> str:
        """Форматирует структуру курса по секциям без AI."""
        if not sections:
            return "Структура курса не найдена."

        lines = ["<b>📚 Структура курса:</b>\n"]
        for sec in sections:
            title = sec.get("title", "")
            acts = sec.get("activities", [])
            if not acts:
                continue
            if title:
                lines.append(f"\n<b>{title}</b>")
            for a in acts:
                icon = TASK_ICONS.get(a.get("type", "other"), "•")
                mark = "✅" if a.get("completed") else "⬜"
                dl = f" <i>срок: {a['deadline']}</i>" if a.get("deadline") else ""
                lines.append(f"  {mark} {icon} {a['name']}{dl}")
        return "\n".join(lines)
