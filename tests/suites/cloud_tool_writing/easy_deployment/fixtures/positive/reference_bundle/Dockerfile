# Reference container for inventory-api (stdlib-only Python HTTP service).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Dependencies first for layer caching (requirements.txt is empty: stdlib only).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code and runtime config.
COPY main.py ./
COPY inventory/ ./inventory/
COPY config/ ./config/

RUN useradd --create-home --uid 10001 appuser
USER appuser

# Cloud Run injects PORT (8080 by default); main.py listens on $PORT.
EXPOSE 8080
CMD ["python", "main.py"]
