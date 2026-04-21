"""
run.py — быстрый запуск агента.

Запусти: python run.py
"""

from navigator import Navigator

print("🚀 Запускаю агент для campus.fa.ru...")
print("   Браузер откроется — можно наблюдать за работой агента\n")

nav = Navigator(headless=False)  # False = видишь браузер
nav.run_full_scan()
