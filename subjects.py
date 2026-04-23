"""
subjects.py — реестр предметов с флагами, базой преподавателей и статистикой.
"""

import os
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime

NOTES_DIR = "notes"
REGISTRY_FILE = "subjects.json"
TEACHERS_FILE = "teachers.json"
STATS_FILE = "stats.json"


@dataclass
class Subject:
    name: str
    subject_id: str
    webinar_url: str = ""
    event_ids: list = field(default_factory=list)
    quiz_urls: list = field(default_factory=list)
    assignment_urls: list = field(default_factory=list)
    schedule: list = field(default_factory=list)
    duration_minutes: int = 90
    notes_files: list = field(default_factory=list)
    teacher_requirements: str = ""
    teacher_name: str = ""
    teacher_email: str = ""

    # Новые флаги
    external_platform: bool = False      # Курс на неподдерживаемой платформе (Stepik и т.п.)
    external_url: str = ""               # Куда ведёт (если external)
    needs_enrollment: bool = False       # Нужна запись на курс
    completed: bool = False              # Предмет полностью сдан (пропускаем)
    semester: str = ""                   # "1" или "2" — для фильтра по семестру
    source_platform: str = ""            # Базовый URL платформы (пусто = campus.fa.ru, иначе напр. https://online.fa.ru)
    course_url: str = ""                 # Прямая ссылка на страницу курса в Moodle

    # Информация по тестам/заданиям (словари: url -> статус)
    quiz_status: dict = field(default_factory=dict)          # {url: "new"|"in_progress"|"done"}
    quiz_attempts: dict = field(default_factory=dict)        # {url: max_attempts_int}
    assignment_status: dict = field(default_factory=dict)    # {url: "new"|"submitted"|"graded"}
    assignment_deadlines: dict = field(default_factory=dict) # {url: iso_date_string}

    def get_full_knowledge(self) -> str:
        all_notes = []
        for filepath in self.notes_files:
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    all_notes.append(content)
        return "\n\n---\n\n".join(all_notes) if all_notes else ""

    def get_context_for_ai(self) -> str:
        parts = []
        if self.teacher_name.strip():
            parts.append(f"ПРЕПОДАВАТЕЛЬ: {self.teacher_name}")
        if self.teacher_requirements.strip():
            parts.append(f"ТРЕБОВАНИЯ ПРЕПОДАВАТЕЛЯ:\n{self.teacher_requirements.strip()}")
        knowledge = self.get_full_knowledge()
        if knowledge:
            parts.append(f"КОНСПЕКТЫ ЛЕКЦИЙ:\n{knowledge[:25000]}")
        return "\n\n".join(parts)

    def add_notes_file(self, filepath: str):
        if filepath not in self.notes_files:
            self.notes_files.append(filepath)

    def get_context_for_topic(self, topic: str = "") -> str:
        """Возвращает конспект предмета, обрезанный до 3000 символов.
        Фильтрация по теме — в будущем; сейчас отдаём полный конспект."""
        return self.get_full_knowledge()[:3000]


class SubjectRegistry:
    def __init__(self):
        os.makedirs(NOTES_DIR, exist_ok=True)
        self.subjects: dict = {}
        self._load()

    def add(self, subject: Subject):
        self.subjects[subject.subject_id] = subject
        self._save()
        print(f"✅ Добавлен предмет: {subject.name}")

    def get(self, subject_id: str) -> Subject:
        return self.subjects.get(subject_id)

    def all(self, active_only: bool = False) -> list:
        """active_only=True — только активные (не completed, не external)."""
        subjects = list(self.subjects.values())
        if active_only:
            subjects = [s for s in subjects if not s.completed and not s.external_platform]
        return subjects

    def add_notes(self, subject_id: str, notes_file: str):
        subject = self.get(subject_id)
        if subject:
            subject.add_notes_file(notes_file)
            self._save()

    def update_requirements(self, subject_id: str, requirements: str,
                            teacher: str = "", email: str = ""):
        subject = self.get(subject_id)
        if subject:
            subject.teacher_requirements = requirements
            if teacher:
                subject.teacher_name = teacher
            if email:
                subject.teacher_email = email
            self._save()

    def mark_external(self, subject_id: str, external_url: str = ""):
        subject = self.get(subject_id)
        if subject:
            subject.external_platform = True
            subject.external_url = external_url
            self._save()

    def mark_needs_enrollment(self, subject_id: str):
        subject = self.get(subject_id)
        if subject:
            subject.needs_enrollment = True
            self._save()

    def mark_completed(self, subject_id: str):
        subject = self.get(subject_id)
        if subject:
            subject.completed = True
            self._save()

    def set_quiz_status(self, subject_id: str, quiz_url: str, status: str, max_attempts: int = None):
        subject = self.get(subject_id)
        if subject:
            subject.quiz_status[quiz_url] = status
            if max_attempts is not None:
                subject.quiz_attempts[quiz_url] = max_attempts
            self._save()

    def set_assignment_status(self, subject_id: str, url: str, status: str, deadline: str = ""):
        subject = self.get(subject_id)
        if subject:
            subject.assignment_status[url] = status
            if deadline:
                subject.assignment_deadlines[url] = deadline
            self._save()

    def remove(self, subject_id: str) -> bool:
        if subject_id in self.subjects:
            del self.subjects[subject_id]
            self._save()
            return True
        return False

    def _save(self):
        data = {sid: asdict(s) for sid, s in self.subjects.items()}
        with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load(self):
        if not os.path.exists(REGISTRY_FILE):
            return
        try:
            with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for sid, sdata in data.items():
                # Совместимость со старыми данными
                defaults = {
                    "teacher_requirements": "", "teacher_name": "", "teacher_email": "",
                    "external_platform": False, "external_url": "",
                    "needs_enrollment": False, "completed": False, "semester": "",
                    "source_platform": "",
                    "course_url": "",
                    "quiz_status": {}, "quiz_attempts": {},
                    "assignment_status": {}, "assignment_deadlines": {},
                }
                for k, v in defaults.items():
                    sdata.setdefault(k, v)
                self.subjects[sid] = Subject(**sdata)
            print(f"📖 Загружено предметов: {len(self.subjects)}")
        except Exception as e:
            print(f"⚠️ Ошибка загрузки реестра: {e}")


# ─── База преподавателей ──────────────────────────────────────

class TeacherRegistry:
    """
    Отдельная база преподавателей.
    Один препод может вести несколько курсов — бот видит общий стиль.
    """

    def __init__(self):
        self.teachers: dict = {}
        self._load()

    def add_or_update(self, name: str, email: str = "", requirements: str = "",
                      courses: list = None):
        key = self._normalize(name)
        if not key:
            return
        existing = self.teachers.get(key, {})
        self.teachers[key] = {
            "name": name,
            "email": email or existing.get("email", ""),
            "requirements_samples": list(set(
                (existing.get("requirements_samples") or []) +
                ([requirements] if requirements else [])
            ))[:5],
            "courses": list(set((existing.get("courses") or []) + (courses or []))),
        }
        self._save()

    def get(self, name: str) -> dict:
        return self.teachers.get(self._normalize(name), {})

    def all(self) -> dict:
        return self.teachers

    def _normalize(self, name: str) -> str:
        return name.strip().lower() if name else ""

    def _save(self):
        with open(TEACHERS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.teachers, f, ensure_ascii=False, indent=2)

    def _load(self):
        if not os.path.exists(TEACHERS_FILE):
            return
        try:
            with open(TEACHERS_FILE, "r", encoding="utf-8") as f:
                self.teachers = json.load(f)
        except Exception:
            self.teachers = {}


# ─── Статистика ───────────────────────────────────────────────

class Stats:
    """Статистика работы бота."""

    def __init__(self):
        self.data = {
            "quizzes_passed": 0,
            "quizzes_skipped": 0,
            "assignments_submitted": 0,
            "lectures_attended": 0,
            "by_subject": {},
        }
        self._load()

    def record_quiz(self, subject_id: str, status: str):
        if status == "passed":
            self.data["quizzes_passed"] += 1
        elif status == "skipped":
            self.data["quizzes_skipped"] += 1
        self._ensure_subject(subject_id)
        self.data["by_subject"][subject_id]["quizzes"] = \
            self.data["by_subject"][subject_id].get("quizzes", 0) + 1
        self._save()

    def record_assignment(self, subject_id: str):
        self.data["assignments_submitted"] += 1
        self._ensure_subject(subject_id)
        self.data["by_subject"][subject_id]["assignments"] = \
            self.data["by_subject"][subject_id].get("assignments", 0) + 1
        self._save()

    def record_lecture(self, subject_id: str, words: int):
        self.data["lectures_attended"] += 1
        self._ensure_subject(subject_id)
        self.data["by_subject"][subject_id]["lectures"] = \
            self.data["by_subject"][subject_id].get("lectures", 0) + 1
        self.data["by_subject"][subject_id]["total_words"] = \
            self.data["by_subject"][subject_id].get("total_words", 0) + words
        self._save()

    def summary(self) -> str:
        d = self.data
        total = d["quizzes_passed"] + d["quizzes_skipped"]
        pct = int(d["quizzes_passed"] / total * 100) if total else 0
        lines = [
            "<b>📊 Статистика работы бота</b>\n",
            f"Тестов сдано: <b>{d['quizzes_passed']}</b>",
            f"Тестов пропущено: <b>{d['quizzes_skipped']}</b>",
            f"Успешных ответов: <b>{pct}%</b>",
            f"Заданий отправлено: <b>{d['assignments_submitted']}</b>",
            f"Лекций прослушано: <b>{d['lectures_attended']}</b>",
        ]
        if d["by_subject"]:
            lines.append("\n<b>По предметам:</b>")
            for sid, s in d["by_subject"].items():
                parts = []
                if s.get("quizzes"):
                    parts.append(f"тестов: {s['quizzes']}")
                if s.get("assignments"):
                    parts.append(f"заданий: {s['assignments']}")
                if s.get("lectures"):
                    parts.append(f"лекций: {s['lectures']}")
                if parts:
                    lines.append(f"  • {sid}: {', '.join(parts)}")
        return "\n".join(lines)

    def _ensure_subject(self, subject_id: str):
        if subject_id not in self.data["by_subject"]:
            self.data["by_subject"][subject_id] = {}

    def _save(self):
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def _load(self):
        if not os.path.exists(STATS_FILE):
            return
        try:
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        except Exception:
            pass
