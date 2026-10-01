FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y ffmpeg curl unzip ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Deno — yt-dlp YouTube uchun kerak bo'lishi mumkin
RUN curl -fsSL https://deno.land/install.sh | sh

ENV DENO_INSTALL=/root/.deno
ENV PATH="/root/.deno/bin:$PATH"

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p downloads

CMD ["python", "bot.py"]