FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    VAULT_CONFIG_PATH=/data/config.json

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Config (secrets) lives on a volume so rebuilds don't wipe it.
VOLUME ["/data"]
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
