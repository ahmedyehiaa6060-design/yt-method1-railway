from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
import subprocess
import os
import uuid
import time
import threading

app = FastAPI(title="YT Segment Cutter - Method 4")

TEMP_DIR = "/tmp/yt_segments"
os.makedirs(TEMP_DIR, exist_ok=True)


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
    <head><title>YT Segment Cutter - Method 4</title></head>
    <body style="font-family:sans-serif; max-width:600px; margin:50px auto;">
        <h1>YT Segment Cutter - Method 4</h1>
        <p>CLI get-url + ffmpeg stream (no full download, no re-encoding)</p>
    </body>
    </html>
    """


@app.get("/health")
def health():
    return {"status": "ok", "method": "4 - CLI get-url + ffmpeg stream"}


@app.post("/cut")
def cut_video(req: CutRequest):
    if req.quality not in [360, 480, 720, 1080, 1440, 2160]:
        raise HTTPException(400, "quality must be 360, 480, 720, 1080, 1440, or 2160")

    file_id = str(uuid.uuid4())[:8]
    output_path = os.path.join(TEMP_DIR, f"{file_id}.mkv")

    # الخطوة 1: استخراج الروابط بـ CLI (زي الطريقة 3 اللي نجحت)
    try:
        video_url = subprocess.check_output([
            "yt-dlp", "-f", f"bestvideo[height<={req.quality}]",
            "--get-url", "--no-playlist", req.url
        ], text=True, timeout=30).strip()

        audio_url = subprocess.check_output([
            "yt-dlp", "-f", "bestaudio",
            "--get-url", "--no-playlist", req.url
        ], text=True, timeout=30).strip()
    except Exception as e:
        raise HTTPException(500, f"get-url failed: {str(e)}")

    # الخطوة 2: ffmpeg يقص من الـ stream مباشرة
    # -c copy = لا re-encoding = رام منخفض
    # mkv = يدعم كل الـ codecs
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-ss", req.start_time,
        "-to", req.end_time,
        "-i", video_url,
        "-ss", req.start_time,
        "-to", req.end_time,
        "-i", audio_url,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c", "copy",
        output_path
    ]

    start = time.time()
    result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=120)
    elapsed = time.time() - start

    if result.returncode != 0:
        raise HTTPException(500, f"ffmpeg failed: {result.stderr[-300:]}")

    if not os.path.exists(output_path):
        raise HTTPException(500, "output file not found")

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"✅ {size_mb:.1f}MB | {elapsed:.0f}s | {req.quality}p")

    return FileResponse(
        output_path,
        media_type="video/x-matroska",
        filename=f"cut_{file_id}.mkv"
    )
