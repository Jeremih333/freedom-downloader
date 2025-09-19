FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

# system deps for yt-dlp/ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    git \
    curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

RUN pip install --upgrade pip && pip install -r requirements.txt

ENV PORT=10000

# default: run web by default (Procfile per Render overrides)
CMD ["sh", "-c", "python bot/main.py"]
