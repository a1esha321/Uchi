FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN PLAYWRIGHT_BROWSERS_PATH=/ms-playwright playwright install chromium

COPY . .

CMD ["python", "telegram_bot.py"]
