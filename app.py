from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
import yt_dlp
import os
import uuid
import time
import shutil
import threading
import subprocess

app = FastAPI(title="YT Segment Cutter - Method 5 (Deno + Cookies + Custom FFmpeg)")

TEMP_DIR = "/tmp/yt_segments"
os.makedirs(TEMP_DIR, exist_ok=True)

COOKIE_FILE_PATH = "/tmp/cookies.txt"


def init_cookies():
    """كتابة الكوكيز من متغيرات البيئة أو نقلها من مجلد السيرفر عند الإقلاع"""
    cookies_env = os.environ.get("YOUTUBE_COOKIES")
    if cookies_env:
        try:
            with open(COOKIE_FILE_PATH, "w", encoding="utf-8") as f:
                f.write(cookies_env.strip())
            print("🔑 cookies.txt written from YOUTUBE_COOKIES env variable.")
        except Exception as e:
            print(f"⚠️ Failed to write cookies from env: {e}")
    else:
        # خيار بديل إذا قام برفع ملف cookies.txt مباشرة في المجلد
        if os.path.exists("cookies.txt"):
            try:
                shutil.copy("cookies.txt", COOKIE_FILE_PATH)
                print("🔑 cookies.txt copied from project root.")
            except Exception as e:
                print(f"⚠️ Failed to copy local cookies.txt: {e}")
        else:
            print("⚠️ Warning: No cookies.txt found or YOUTUBE_COOKIES env variable is not set!")


init_cookies()


def cleanup_old_files():
    while True:
        now = time.time()
        for f in os.listdir(TEMP_DIR):
            filepath = os.path.join(TEMP_DIR, f)
            if os.path.isfile(filepath) and now - os.path.getmtime(filepath) > 600:
                try:
                    os.remove(filepath)
                except:
                    pass
        time.sleep(60)


threading.Thread(target=cleanup_old_files, daemon=True).start()


class CutRequest(BaseModel):
    url: str
    start_time: str
    end_time: str
    quality: int = 720


def parse_time_to_seconds(time_str: str) -> float:
    """تحويل صيغ الوقت (HH:MM:SS أو MM:SS أو ثوانٍ مجردة) إلى ثوانٍ float"""
    try:
        return float(time_str)
    except ValueError:
        pass

    parts = time_str.split(':')
    if len(parts) == 3:
        h, m, s = parts
        return float(h) * 3600 + float(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return float(m) * 60 + float(s)
    else:
        raise ValueError(f"Invalid time format: {time_str}")


@app.get("/", response_class=HTMLResponse)
def home():
    has_cookies = os.path.exists(COOKIE_FILE_PATH) and os.path.getsize(COOKIE_FILE_PATH) > 0
    cookies_status = "<span style='color: green;'>Loaded (نشطة)</span>" if has_cookies else "<span style='color: red;'>Missing (غير متوفرة)</span>"
    
    return f"""
    <html>
    <head>
        <title>YT Segment Cutter - Custom FFmpeg</title>
        <style>
            body {{ font-family: sans-serif; max-width: 600px; margin: 50px auto; line-height: 1.6; }}
            h1 {{ color: #2c3e50; }}
            code {{ background: #eee; padding: 2px 5px; border-radius: 3px; }}
            .status-box {{ padding: 15px; background: #f8f9fa; border-radius: 5px; border: 1px solid #ddd; }}
        </style>
    </head>
    <body>
        <h1>YT Segment Cutter</h1>
        <p>Running Custom FFmpeg Transcoding using <code>yt-dlp</code> Nightly Info Extractor.</p>
        <div class="status-box">
            <strong>Cookies Status:</strong> {cookies_status}
        </div>
    </body>
    </html>
    """


@app.get("/health")
def health():
    has_cookies = os.path.exists(COOKIE_FILE_PATH) and os.path.getsize(COOKIE_FILE_PATH) > 0
    return {
        "status": "ok", 
        "method": "Custom FFmpeg Transcoder",
        "cookies_loaded": has_cookies
    }


@app.post("/cut")
def cut_video(req: CutRequest):
    if req.quality not in [360, 480, 720, 1080, 1440, 2160]:
        raise HTTPException(400, "quality must be 360, 480, 720, 1080, 1440, or 2160")

    try:
        start_sec = parse_time_to_seconds(req.start_time)
        end_sec = parse_time_to_seconds(req.end_time)
    except Exception as e:
        raise HTTPException(400, f"Invalid start_time or end_time: {str(e)}")

    if start_sec >= end_sec:
        raise HTTPException(400, "start_time must be less than end_time")

    duration_sec = end_sec - start_sec
    file_id = str(uuid.uuid4())[:8]
    output_path = os.path.join(TEMP_DIR, f"{file_id}.mp4")

    # 1. تهيئة خيارات استخراج المعلومات من yt-dlp لتفادي الحظر
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'source_address': '0.0.0.0',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
        }
    }

    if os.path.exists(COOKIE_FILE_PATH) and os.path.getsize(COOKIE_FILE_PATH) > 0:
        ydl_opts['cookiefile'] = COOKIE_FILE_PATH

    print(f"⏳ Extracting stream URLs for quality {req.quality}p...")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=False)
    except Exception as e:
        raise HTTPException(500, f"Failed to extract video info: {str(e)}")

    # 2. تصفية واختيار بث الفيديو المناسب (منطق كود العميل)
    video_formats = [
        f for f in info.get('formats', [])
        if f.get('vcodec') != 'none'
        and f.get('acodec') == 'none'
        and f.get('ext') == 'mp4'
        and (f.get('height', 0) <= req.quality)
    ]
    video_formats.sort(key=lambda x: x.get('height', 0), reverse=True)

    # اختيار أعلى جودة mp4 متاحة كبديل إن لم يجد المطلوب
    if not video_formats:
        print("⚠️ No matching MP4 format found. Falling back to any MP4 video stream.")
        video_formats = [
            f for f in info.get('formats', [])
            if f.get('vcodec') != 'none'
            and f.get('acodec') == 'none'
            and f.get('ext') == 'mp4'
        ]
        video_formats.sort(key=lambda x: x.get('height', 0), reverse=True)

    if not video_formats:
        raise HTTPException(500, "Could not find a suitable MP4 video stream")

    video_url = video_formats[0]['url']
    selected_height = video_formats[0].get('height', 0)
    print(f"🎬 Selected Video Stream: {selected_height}p")

    # 3. تصفية واختيار بث الصوت بأعلى جودة
    audio_formats = [
        f for f in info.get('formats', [])
        if f.get('acodec') != 'none'
        and f.get('vcodec') == 'none'
    ]
    audio_formats.sort(key=lambda x: x.get('abr', 0), reverse=True)

    if not audio_formats:
        raise HTTPException(500, "Could not find a suitable audio stream")

    audio_url = audio_formats[0]['url']

    # 4. تشغيل المعالجة والقص عبر ffmpeg باستخدام المعاملات الموفرة للموارد
    print(f"🎬 Processing segment: {req.start_time} to {req.end_time}...")
    start_time_proc = time.time()
    
    ffmpeg_cmd = [
        'ffmpeg', '-y',
        '-ss', str(start_sec), '-i', video_url,
        '-ss', str(start_sec), '-i', audio_url,
        '-t', str(duration_sec),
        '-c:v', 'libx264',
        '-preset', 'ultrafast',   # ultrafast يقلل استهلاك الرام لـ 150MB فقط ويمنع الـ OOM
        '-crf', '20',             # جودة عالية جداً وصورة ممتازة
        '-threads', '1',          # خيط معالجة واحد لمنع تضخم الرام في Railway
        '-c:a', 'aac', '-b:a', '192k',
        '-movflags', '+faststart',
        output_path
    ]

    result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    elapsed = time.time() - start_time_proc

    if result.returncode != 0:
        if os.path.exists(output_path):
            try: os.remove(output_path)
            except: pass
        raise HTTPException(500, f"FFmpeg processing failed: {result.stderr}")

    if not os.path.exists(output_path):
        raise HTTPException(500, "Output MP4 file was not generated")

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"✅ Success! {size_mb:.2f}MB | {elapsed:.1f}s | {selected_height}p MP4")

    return FileResponse(
        output_path,
        media_type="video/mp4",
        filename=f"cut_{file_id}.mp4"
    )
