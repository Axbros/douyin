ARG PYTHON_BASE_IMAGE=python:3.12-slim-bookworm
FROM ${PYTHON_BASE_IMAGE}

ARG PLAYWRIGHT_VERSION=1.62.0
ARG DEBIAN_MIRROR=https://mirrors.aliyun.com/debian
ARG DEBIAN_SECURITY_MIRROR=https://mirrors.aliyun.com/debian-security
ARG PYPI_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright
ARG PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=120000

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/backend:/app \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY backend/requirements.txt /tmp/requirements.txt
RUN find /etc/apt -type f \( -name '*.list' -o -name '*.sources' \) -exec sed -i \
      -e "s|http://deb.debian.org/debian-security|${DEBIAN_SECURITY_MIRROR}|g" \
      -e "s|https://deb.debian.org/debian-security|${DEBIAN_SECURITY_MIRROR}|g" \
      -e "s|http://security.debian.org/debian-security|${DEBIAN_SECURITY_MIRROR}|g" \
      -e "s|https://security.debian.org/debian-security|${DEBIAN_SECURITY_MIRROR}|g" \
      -e "s|http://deb.debian.org/debian|${DEBIAN_MIRROR}|g" \
      -e "s|https://deb.debian.org/debian|${DEBIAN_MIRROR}|g" \
      {} +
RUN python -m pip install --no-cache-dir --timeout 120 --retries 10 --index-url "${PYPI_INDEX_URL}" --upgrade pip \
    && python -m pip install --no-cache-dir --timeout 120 --retries 10 --index-url "${PYPI_INDEX_URL}" -r /tmp/requirements.txt \
    && python -m pip install --no-cache-dir --timeout 120 --retries 10 --index-url "${PYPI_INDEX_URL}" "playwright==${PLAYWRIGHT_VERSION}" \
    && apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install -y --no-install-recommends xvfb xauth fonts-noto-cjk fonts-liberation curl \
    && python -m playwright install-deps chromium \
    && (PLAYWRIGHT_DOWNLOAD_HOST="${PLAYWRIGHT_DOWNLOAD_HOST}" \
        PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT="${PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT}" \
        python -m playwright install chromium \
        || PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT="${PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT}" \
        python -m playwright install chromium) \
    && rm -rf /var/lib/apt/lists/*

COPY backend /app/backend
COPY src /app/src

WORKDIR /app/backend

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
