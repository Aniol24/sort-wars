FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    gnupg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright + Chromium (arm64 supported since Playwright 1.40+)
RUN playwright install-deps chromium && playwright install chromium

COPY . .

CMD ["python", "src/run.py"]
