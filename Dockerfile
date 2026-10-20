FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PORT=8080 \
    HOST=0.0.0.0 \
    DEVBENCH_STATE_DIR=/tmp/devbench_state \
    GOOGLE_CLOUD_PROJECT="" \
    VERTEX_PROJECT_ID=""

WORKDIR /app

# Copy package metadata and source code
COPY pyproject.toml README.md SCENARIOS.MD /app/
COPY configs/ /app/configs/
COPY src/ /app/src/
COPY tests/ /app/tests/

# Install devbench in editable mode so /app source and static assets are directly served
RUN pip install --no-cache-dir -e . google-auth

EXPOSE 8080

CMD ["python3", "-m", "devbench.ui.web.server"]
