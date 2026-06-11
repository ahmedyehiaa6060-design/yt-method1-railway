from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
import yt_dlp
from yt_dlp.utils import download_range_func
import os
import uuid
import time
import shutil
import threading

app = FastAPI(title="YT Segment Cutter - Method 5 (Deno + Cookies)")

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
        <title>YT Segment Cutter - Method 5 (Deno + Cookies)</title>
        <style>
            body {{ font-family: sans-serif; max-width: 600px; margin: 50px auto; line-height: 1.6; }}
            h1 {{ color: #2c3e50; }}
            code {{ background: #eee; padding: 2px 5px; border-radius: 3px; }}
            .status-box {{ padding: 15px; background: #f8f9fa; border-radius: 5px; border: 1px solid #ddd; }}
        </style>
    </head>
    <body>
        <h1>YT Segment Cutter</h1>
        <p>Running Method 5 (Deno + Cookies) using <code>yt-dlp</code> Nightly Python API.</p>
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
        "method": "Method 5 (Deno + Cookies)",
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

    file_id = str(uuid.uuid4())[:8]
    outtmpl_path = os.path.join(TEMP_DIR, f"{file_id}.%(ext)s")
    output_path = os.path.join(TEMP_DIR, f"{file_id}.mp4")

    # تحديد ذكي لدقة القص بناء على الجودة المطلوبة لتفادي الانهيار OOM
    # الجودات العالية جدا (أكبر من 1080) تتطلب رام ضخم لإعادة الترميز
    force_keyframes = True
    if req.quality > 1080:
        force_keyframes = False
        print(f"⚠️ High quality ({req.quality}p) requested. Disabling force_keyframes_at_cuts to prevent OOM crash.")

    # إعدادات التخطي المعتمدة على Deno والكوكيز
    ydl_opts = {
        # 1. الجودة والصيغة والدمج
        'format': f'bestvideo[ext=mp4][height<={req.quality}]+bestaudio[ext=m4a]/best[ext=mp4]/best[height<={req.quality}]',
        'merge_output_format': 'mp4',
        'outtmpl': outtmpl_path,
        
        # 2. تحديد مجال القص بدقة
        'download_ranges': download_range_func(None, [(start_sec, end_sec)]),
        'force_keyframes_at_cuts': force_keyframes,
        
        # 3. إجبار الاتصال عبر IPv4 لتفادي حظر IPv6 الجماعي في السيرفرات
        'source_address': '0.0.0.0',
        
        # 4. محاكاة متصفح حديث
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        },
        
        # 5. تحديد مسارات ffmpeg وتحديد عدد الـ threads إلى 1 لتفادي استهلاك الرامات (OOM Crash)
        'external_downloader_args': {
            'ffmpeg': ['-threads', '1']
        },
        'postprocessor_args': {
            'ffmpeg': ['-threads', '1']
        },
        
        'quiet': True,
        'no_warnings': True,
    }

    # 6. تمرير ملف الكوكيز إذا تم تهيئته
    if os.path.exists(COOKIE_FILE_PATH) and os.path.getsize(COOKIE_FILE_PATH) > 0:
        ydl_opts['cookiefile'] = COOKIE_FILE_PATH
        print("💡 Using cookies.txt for this download request.")

    start = time.time()
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([req.url])
    except Exception as e:
        if os.path.exists(output_path):
            try: os.remove(output_path)
            except: pass
        raise HTTPException(500, f"Download failed: {str(e)}")
    
    elapsed = time.time() - start

    if not os.path.exists(output_path):
        raise HTTPException(500, "Output file was not generated by yt-dlp")

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"✅ {size_mb:.2f}MB | {elapsed:.1f}s | {req.quality}p (Method 5 Deno+Cookies)")

    return FileResponse(
        output_path,
        media_type="video/mp4",
        filename=f"cut_{file_id}.mp4"
    )
