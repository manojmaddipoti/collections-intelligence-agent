FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --create-home appuser

COPY --chown=appuser:appuser . .
RUN mkdir -p /app/data && chown appuser:appuser /app/data

USER appuser

EXPOSE 8000

CMD ["sh", "-c", "python scripts/ensure_data.py && exec uvicorn fast_api_app:app --host 0.0.0.0 --port ${PORT}"]
