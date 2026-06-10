from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
import subprocess
import os
import uuid
import time
import threading

app = FastAPI(title="YT Segment Cutter - Oxylabs Paid Proxy")

TEMP_DIR = "/tmp/yt_segments"
os.makedirs(TEMP_DIR, exist_ok=True)

# بروكسي Oxylabs المدفوع - سريع ومستقر 100% ويتخطى الحظر مباشرة
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


@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
    <head><title>YT Segment Cutter - Oxylabs Proxy</title></head>
    <body style="font-family:sans-serif; max-width:600px; margin:50px auto;">
        <h1>YT Segment Cutter (Oxylabs Paid Proxy)</h1>
        <p>CLI --download-sections running on high-speed premium proxy</p>
    </body>
    </html>
    """


@app.get("/health")
def health():
    return {"status": "ok", "method": "3 Optimized + Premium Oxylabs Proxy"}


@app.post("/cut")
def cut_video(req: CutRequest):
    if req.quality not in [360, 480, 720, 1080, 1440, 2160]:
        raise HTTPException(400, "quality must be 360, 480, 720, 1080, 1440, or 2160")

    file_id = str(uuid.uuid4())[:8]
    output_path = os.path.join(TEMP_DIR, f"{file_id}.mp4")

    # تحديد صيغة تضمن أن يكون الفيديو H264 والصوت AAC ليعمل الـ MP4 على جميع المشغلات بدون مشاكل
    format_str = f"bestvideo[ext=mp4][height<={req.quality}]+bestaudio[ext=m4a]/best[ext=mp4]/best[height<={req.quality}]"

    cmd = [
        "yt-dlp",
        "-f", format_str,
        "--download-sections", f"*{req.start_time}-{req.end_time}",
        "--merge-output-format", "mp4",
        "--proxy", PROXY_URL,
        "-o", output_path,
        "--no-playlist",
        req.url
    ]

    start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    elapsed = time.time() - start

    if result.returncode != 0:
        raise HTTPException(500, f"download failed: {result.stderr[-500:]}")

    if not os.path.exists(output_path):
        raise HTTPException(500, "output file not found")

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"✅ {size_mb:.1f}MB | {elapsed:.0f}s | {req.quality}p (Via Oxylabs)")

    return FileResponse(
        output_path,
        media_type="video/mp4",
        filename=f"cut_{file_id}.mp4"
    )
