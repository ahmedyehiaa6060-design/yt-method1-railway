from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
import yt_dlp
from yt_dlp.utils import download_range_func
import os
import uuid
import time
import threading

app = FastAPI(title="YT Segment Cutter - Method 1")

TEMP_DIR = "/tmp/yt_segments"
os.makedirs(TEMP_DIR, exist_ok=True)


# تنظيف الملفات الأقدم من 10 دقائق — ضروري لحماية الـ storage (1 GB فقط)
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
    start_seconds: float
    end_seconds: float
    quality: int = 720


@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
    <head><title>YT Segment Cutter</title></head>
    <body style="font-family:sans-serif; max-width:600px; margin:50px auto; direction:rtl;">
        <h1>🎬 YT Segment Cutter</h1>
        <p>Method 1: yt-dlp Python API</p>
        <p>POST /cut</p>
        <pre>{
  "url": "https://www.youtube.com/watch?v=...",
  "start_seconds": 10,
  "end_seconds": 30,
  "quality": 720
}</pre>
        <p>GET /health</p>
    </body>
    </html>
    """


@app.get("/health")
def health():
    return {"status": "ok", "method": "1 - yt-dlp Python API"}


@app.post("/cut")
def cut_video(req: CutRequest):
    # حماية الموارد
    duration = req.end_seconds - req.start_seconds
    if duration <= 0:
        raise HTTPException(400, "end must be after start")
    if duration > 300:
        raise HTTPException(400, "max 5 minutes per cut")
    if req.quality not in [360, 480, 720, 1080, 1440, 2160]:
        raise HTTPException(400, "quality must be 360, 480, 720, 1080, 1440, or 2160")

    file_id = str(uuid.uuid4())[:8]
    output_template = os.path.join(TEMP_DIR, f"{file_id}")

    ydl_opts = {
        'format': f'bestvideo[height<={req.quality}]+bestaudio/best[height<={req.quality}]',
        'download_ranges': download_range_func(None, [(req.start_seconds, req.end_seconds)]),
        'force_keyframes_at_cuts': True,
        'merge_output_format': 'mp4',
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
    }

    start = time.time()
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=True)
            title = info.get('title', 'video')
    except Exception as e:
        raise HTTPException(500, f"download failed: {str(e)}")

    elapsed = time.time() - start

    # البحث عن الملف الناتج
    actual_file = None
    for f in os.listdir(TEMP_DIR):
        if f.startswith(file_id):
            actual_file = os.path.join(TEMP_DIR, f)
            break

    if not actual_file or not os.path.exists(actual_file):
        raise HTTPException(500, "output file not found")

    size_mb = os.path.getsize(actual_file) / (1024 * 1024)
    print(f"✅ {title} | {size_mb:.1f}MB | {elapsed:.0f}s | {req.quality}p")

    return FileResponse(
        actual_file,
        media_type="video/mp4",
        filename=f"{title}_cut.mp4"
    )
