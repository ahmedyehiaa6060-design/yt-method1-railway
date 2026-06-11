FROM python:3.11-slim

# تثبيت curl و unzip لتنزيل Deno، و ffmpeg للقص والدمج
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl unzip && rm -rf /var/lib/apt/lists/*

# تثبيت Deno (محرك الجافا سكربت المطلوب لتخطي تحديات يوتيوب الأمنية)
RUN curl -fsSL https://deno.land/x/install/install.sh | sh
ENV DENO_INSTALL="/root/.deno"
ENV PATH="${DENO_INSTALL}/bin:${PATH}"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# تثبيت نسخة nightly الأحدث من yt-dlp
RUN pip install -U --pre "yt-dlp[default]"

# نسخ جميع ملفات المشروع (بما فيها cookies.txt إن وُجدت)
COPY . .

EXPOSE 8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
