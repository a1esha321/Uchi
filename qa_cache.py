"""
qa_cache.py — кэш вопросов/ответов для тестов.
Избегает повторных запросов к Groq для одинаковых вопросов.
"""

import json
import os
import hashlib

CACHE_FILE = "qa_cache.json"


class QACache:
    def __init__(self):
        self._cache: dict = {}
        self._hits = 0
        self._misses = 0
        self._load()

    def _key(self, question: str, options: list) -> str:
        text = question.strip() + "\n" + "\n".join(str(o) for o in options)
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def get(self, question: str, options: list = None) -> tuple:
        """Возвращает (answer, confidence) или None если нет в кэше."""
        key = self._key(question, options or [])
        entry = self._cache.get(key)
        if entry is not None:
            self._hits += 1
            return entry["answer"], entry["confidence"]
        self._misses += 1
        return None

    def set(self, question: str, options: list, answer, confidence: float):
        """Сохраняет ответ в кэш (только если confidence >= 0.5)."""
        if confidence < 0.5:
            return
        key = self._key(question, options or [])
        self._cache[key] = {"answer": answer, "confidence": confidence}
        self._save()

    def size(self) -> int:
        return len(self._cache)

    def hit_rate(self) -> str:
        total = self._hits + self._misses
        pct = int(self._hits / total * 100) if total else 0
        return f"{self._hits}/{total} ({pct}%)"

    def stats_line(self) -> str:
        return f"Кэш Q&A: {self.size()} записей, попаданий: {self.hit_rate()}"

    def clear(self):
        self._cache = {}
        self._hits = 0
        self._misses = 0
        self._save()
        print("🗑️ Кэш Q&A очищен")

    def _save(self):
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(self._cache, f, ensure_ascii=False, indent=2)

    def _load(self):
        if not os.path.exists(CACHE_FILE):
            return
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                self._cache = json.load(f)
            print(f"📖 Кэш Q&A загружен: {len(self._cache)} записей")
        except Exception as e:
            print(f"⚠️ Ошибка загрузки кэша: {e}")
            self._cache = {}
