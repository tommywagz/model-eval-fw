# syntax=docker/dockerfile:1
ARG PY_VERSION=3.12

# Stage 1: resolve dependencies (none today, but keeps the image reproducible).
FROM python:${PY_VERSION}-slim AS deps
WORKDIR /build
COPY requirements.txt .
RUN pip wheel --no-cache-dir -r requirements.txt -w /wheels

# Stage 2: minimal distroless runtime (ENTRYPOINT is the Python interpreter).
FROM gcr.io/distroless/python3-debian12:nonroot
WORKDIR /app
COPY --from=deps /build/requirements.txt ./requirements.txt
COPY --chown=nonroot:nonroot main.py ./
COPY --chown=nonroot:nonroot inventory ./inventory
COPY --chown=nonroot:nonroot config/settings.json ./config/settings.json
ENV APP_ENV=production
USER nonroot
EXPOSE 8080
CMD ["main.py"]
