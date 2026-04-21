#!/bin/bash
# install.sh — автоустановка агента на сервер
# Запуск: bash install.sh

set -e  # останавливаемся при ошибке

echo ""
echo "================================================"
echo "   УНИ-АГЕНТ — УСТАНОВКА"
echo "================================================"

# 1. Обновление и базовые пакеты
echo ""
echo "[1/6] Устанавливаю системные пакеты..."
apt-get update -q
apt-get install -y -q python3-pip python3-venv git unzip wget curl

# 2. Создаём папку проекта
echo ""
echo "[2/6] Создаю папку проекта..."
mkdir -p /root/uni_agent
cd /root/uni_agent

# 3. Виртуальное окружение
echo ""
echo "[3/6] Создаю виртуальное окружение Python..."
python3 -m venv venv
source venv/bin/activate

# 4. Устанавливаем библиотеки
echo ""
echo "[4/6] Устанавливаю Python библиотеки..."
pip install -q --upgrade pip
pip install -q \
    playwright==1.44.0 \
    anthropic==0.28.0 \
    python-dotenv==1.0.1 \
    apscheduler==3.10.4 \
    requests==2.32.3 \
    python-telegram-bot==21.3 \
    websocket-client==1.8.0

# 5. Устанавливаем браузер Chromium
echo ""
echo "[5/6] Устанавливаю браузер Chromium..."
playwright install chromium --with-deps

# 6. Создаём .env файл
echo ""
echo "[6/6] Создаю файл настроек..."

cat > /root/uni_agent/.env << 'ENVEOF'
# campus.fa.ru
UNI_URL=https://campus.fa.ru
UNI_LOGIN=2511740
UNI_PASSWORD=ЗАПОЛНИ

# Claude API — получить на console.anthropic.com
ANTHROPIC_API_KEY=ЗАПОЛНИ

# МТС Линк
MTS_TOKEN=ЗАПОЛНИ

# Telegram — получить у @BotFather
TELEGRAM_TOKEN=ЗАПОЛНИ
TELEGRAM_USER_ID=750425291

# Stepik
STEPIK_LOGIN=ЗАПОЛНИ
STEPIK_PASSWORD=ЗАПОЛНИ
ENVEOF

# Создаём systemd сервис для автозапуска
cat > /etc/systemd/system/uni-agent.service << 'SERVICEEOF'
[Unit]
Description=Uni Agent Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/uni_agent
ExecStart=/root/uni_agent/venv/bin/python telegram_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICEEOF

systemctl daemon-reload

echo ""
echo "================================================"
echo "   УСТАНОВКА ЗАВЕРШЕНА!"
echo "================================================"
echo ""
echo "Следующие шаги:"
echo ""
echo "1. Загрузи файлы проекта:"
echo "   cd /root/uni_agent"
echo ""
echo "2. Заполни настройки:"
echo "   nano .env"
echo ""
echo "3. Запусти бота:"
echo "   systemctl enable uni-agent"
echo "   systemctl start uni-agent"
echo ""
echo "4. Проверь статус:"
echo "   systemctl status uni-agent"
echo ""
