# Leakproof demo service. Build context: repo root (render.yaml dockerContext: .).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir "fastapi==0.115.6" "uvicorn==0.34.0"
RUN useradd --create-home --uid 10001 demo
WORKDIR /app
COPY service/app.py /app/app.py
COPY service/recorded /app/recorded
USER demo
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-10000}"]
