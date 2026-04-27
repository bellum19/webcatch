# Webhook Inspector — Docker build
FROM python:3.11-slim-bookworm

WORKDIR /app

# Install system deps (for sqlite, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy deps first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Data volume for SQLite DB
VOLUME ["/app/data"]

EXPOSE 9120

ENV PYTHONUNBUFFERED=1
ENV INSPECTOR_PORT=9120
ENV INSPECTOR_HOST=0.0.0.0
ENV LOCAL_LLM_URL=http://host.docker.internal:8081/v1/chat/completions
ENV LOCAL_LLM_MODEL=qwen-local

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9120"]
