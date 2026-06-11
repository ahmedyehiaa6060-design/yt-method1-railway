from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
import yt_dlp
from yt_dlp.utils import download_range_func
import requests
import re
import os
import uuid
import time
import threading

app = FastAPI(title="YT Segment Cutter - Method 1 + Visitor Bypass")

TEMP_DIR = "/tmp/yt_segments"
os.makedirs(TEMP_DIR, exist_ok=True)

# بروكسي Oxylabs المدفوع - Datacenter
PROXY_URL = "http://user-ahmed_8pONX-country-US:H~czA0rftSM~mq2R@dc.oxylabs.io:8000"


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


def get_live_visitor_data():
    """جلب قيمة visitorData تلقائياً من صفحة يوتيوب الرئيسية لتخطي الحظر"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    proxies = {
        'http': PROXY_URL,
        'https': PROXY_URL
    }
    try:
        r = requests.get("https://www.youtube.com/", headers=headers, proxies=proxies, timeout=10)
        # البحث عن visitorData
        match = re.search(r'"visitorData"\s*:\s*"([^"]+)"', r.text)
        if match:
            return match.group(1)
        # البحث في الكوكيز كخيار احتياطي
        visitor_cookie = r.cookies.get("VISITOR_INFO1_LIVE")
        if visitor_cookie:
            return visitor_cookie
    except Exception as e:
        print(f"⚠️ Error fetching visitor_data: {e}")
    return None


@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
    <head>
        <title>YT Segment Cutter - Method 1 + Visitor Bypass</title>
        <style>
            body { font-family: sans-serif; max-width: 600px; margin: 50px auto; line-height: 1.6; }
            h1 { color: #2c3e50; }
            code { background: #eee; padding: 2px 5px; border-radius: 3px; }
        </style>
    </head>
    <body>
        <h1>YT Segment Cutter</h1>
        <p>Running Method 1 (Python API) with dynamic <code>visitor_data</code> bypass and Oxylabs Datacenter Proxy.</p>
    </body>
    </html>
    """


@app.get("/health")
def health():
    return {"status": "ok", "method": "Method 1 (Python API) + Visitor Bypass"}


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
    # قالب الاسم النهائي
    outtmpl_path = os.path.join(TEMP_DIR, f"{file_id}.%(ext)s")
    output_path = os.path.join(TEMP_DIR, f"{file_id}.mp4")

    # جلب الـ visitor_data ديناميكياً لتخطي الحظر
    visitor_data = get_live_visitor_data()
    if not visitor_data:
        # قيمة احتياطية عامة
        visitor_data = "CgtGRzQwaDZXdmxRcyi5p922Bg%3D%3D"
        print(f"⚠️ Using fallback visitor_data: {visitor_data}")
    else:
        print(f"✨ Successfully retrieved live visitor_data: {visitor_data}")

    # خيارات yt-dlp المتوافقة مع الاستراتيجية
    ydl_opts = {
        'format': f'bestvideo[ext=mp4][height<={req.quality}]+bestaudio[ext=m4a]/best[ext=mp4]/best[height<={req.quality}]',
        'download_ranges': download_range_func(None, [(start_sec, end_sec)]),
        'force_keyframes_at_cuts': True,
        'merge_output_format': 'mp4',
        'outtmpl': outtmpl_path,
        'quiet': True,
        'no_warnings': True,
        'proxy': PROXY_URL,
        'extractor_args': {
            'youtube': {
                'visitor_data': [visitor_data],
                'player_skip': ['webpage', 'configs']
            },
            'youtubetab': {
                'skip': ['webpage']
            }
        }
    }

    start = time.time()
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([req.url])
    except Exception as e:
        # تنظيف أي ملفات متبقية في حال الفشل
        if os.path.exists(output_path):
            try: os.remove(output_path)
            except: pass
        raise HTTPException(500, f"Download failed: {str(e)}")
    
    elapsed = time.time() - start

    if not os.path.exists(output_path):
        raise HTTPException(500, "Output file was not generated by yt-dlp")

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"✅ {size_mb:.2f}MB | {elapsed:.1f}s | {req.quality}p (Method 1 + Visitor)")

    return FileResponse(
        output_path,
        media_type="video/mp4",
        filename=f"cut_{file_id}.mp4"
    )
