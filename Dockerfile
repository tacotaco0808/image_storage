FROM python:3.11-slim

# 必要な Linux パッケージを最小限インストール（例: psycopg2などのビルドに必要）
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY app/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .

CMD ["uvicorn","main:app","--reload","--host","0.0.0.0","--port","8000"]