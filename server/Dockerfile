FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY ./app /app/app

# デフォルトの環境変数
ENV CONFIG_FILE=/data/config.json
ENV API_KEY=default-secret-key

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
