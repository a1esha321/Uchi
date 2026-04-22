"""
subjects.py — реестр предметов семестра.
"""

import os
import json
from dataclasses import dataclass, field, asdict

NOTES_DIR = "notes"
REGISTRY_FILE = "subjects.json"


@dataclass
class Subject:
    name: str
    subject_id: str
    webinar_url: str
    event_ids: list
    quiz_urls: list
    assignment_urls: list
    schedule: list
    duration_minutes: int
    notes_files: list = field(default_factory=list)

    def get_full_knowledge(self) -> str:
        all_notes = []
        for filepath in self.notes_files:
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    all_notes.append(content)
        if not all_notes:
            return ""
        combined = "\n\n---\n\n".join(all_notes)
        print(f"{self.name}: загружено {len(all_notes)} конспектов, {len(combined.split())} слов")
        return combined

    def add_notes_file(self, filepath: str):
        if filepath not in self.notes_files:
            self.notes_files.append(filepath)


class SubjectRegistry:
    def __init__(self):
        os.makedirs(NOTES_DIR, exist_ok=True)
        self.subjects: dict = {}
        self._load()

    def add(self, subject: Subject):
        self.subjects[subject.subject_id] = subject
        self._save()
        print(f"Добавлен предмет: {subject.name}")

    def get(self, subject_id: str):
        return self.subjects.get(subject_id)

    def all(self) -> list:
        return list(self.subjects.values())

    def add_notes(self, subject_id: str, notes_file: str):
        subject = self.get(subject_id)
        if subject:
            subject.add_notes_file(notes_file)
            self._save()

    def _save(self):
        data = {sid: asdict(s) for sid, s in self.subjects.items()}
        with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load(self):
        if not os.path.exists(REGISTRY_FILE):
            return
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for sid, sdata in data.items():
            self.subjects[sid] = Subject(**sdata)
        print(f"Загружено предметов: {len(self.subjects)}")
