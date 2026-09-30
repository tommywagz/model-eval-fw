FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Only ship the code; config is 'environment specific'.
COPY main.py ./
COPY inventory/ ./inventory/
USER nobody
EXPOSE 8080
CMD ["python", "main.py"]
