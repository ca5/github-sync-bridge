FROM python:3.11-slim

# Install Node.js for obsidian-headless
RUN apt-get update && apt-get install -y \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install obsidian-headless globally
RUN npm install -g obsidian-headless

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY ./app /app/app

# デフォルトの環境変数
ENV CONFIG_FILE=/data/config.json
ENV API_KEY=default-secret-key

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
