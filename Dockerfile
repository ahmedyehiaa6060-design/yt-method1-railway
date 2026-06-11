FROM python:3.11-slim

# تثبيت ffmpeg و nodejs (مطلوب كـ JS Runtime لتخطي حماية يوتيوب)
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg nodejs && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# تثبيت نسخة nightly الأحدث من yt-dlp
RUN pip install -U --pre "yt-dlp[default]"

COPY app.py .

EXPOSE 8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
