FROM python:3.12-slim-bookworm

ARG PLAYWRIGHT_VERSION=1.63.0

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/backend:/app \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY backend/requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /tmp/requirements.txt \
    && python -m pip install --no-cache-dir "playwright==${PLAYWRIGHT_VERSION}" \
    && apt-get update \
    && apt-get install -y --no-install-recommends xvfb xauth fonts-noto-cjk fonts-liberation curl \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY backend /app/backend
COPY src /app/src

WORKDIR /app/backend

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
