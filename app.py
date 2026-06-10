from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
import subprocess
import os
import uuid
import time
import threading
import yt_dlp

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
        <p>Stream + Re-encode (precise cuts)</p>
    </body>
    </html>
    """


@app.get("/health")
def health():
    return {"status": "ok", "method": "4 - Stream + Re-encode"}


@app.post("/cut")
def cut_video(req: CutRequest):
    if req.quality not in [360, 480, 720, 1080, 1440, 2160]:
        raise HTTPException(400, "quality must be 360, 480, 720, 1080, 1440, or 2160")

    file_id = str(uuid.uuid4())[:8]
    output_path = os.path.join(TEMP_DIR, f"{file_id}.mp4")

    # استخراج الروابط المباشرة
    ydl_opts = {'quiet': True, 'no_warnings': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=False)
    except Exception as e:
        raise HTTPException(500, f"extract failed: {str(e)}")

    video_formats = [f for f in info['formats']
                     if f.get('vcodec', 'none') != 'none'
                     and f.get('height') and f['height'] <= req.quality
                     and f.get('url')]
    audio_formats = [f for f in info['formats']
                     if f.get('acodec', 'none') != 'none'
                     and (f.get('vcodec', 'none') == 'none' or f.get('vcodec') is None)
                     and f.get('url')]

    if not video_formats:
        raise HTTPException(500, "no video formats found")

    video_formats.sort(key=lambda x: (x.get('height', 0), x.get('tbr', 0)), reverse=True)
    audio_formats.sort(key=lambda x: x.get('abr', 0), reverse=True)

    best_video = video_formats[0]
    best_audio = audio_formats[0] if audio_formats else None

    # ffmpeg: stream + re-encode بدقة عالية
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-ss", req.start_time,
        "-to", req.end_time,
        "-i", best_video['url'],
    ]

    if best_audio:
        ffmpeg_cmd += [
            "-ss", req.start_time,
            "-to", req.end_time,
            "-i", best_audio['url'],
            "-map", "0:v:0",
            "-map", "1:a:0",
        ]

    ffmpeg_cmd += [
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        output_path
    ]

    start = time.time()
    result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=300)
    elapsed = time.time() - start

    if result.returncode != 0:
        raise HTTPException(500, f"ffmpeg failed: {result.stderr[-300:]}")

    if not os.path.exists(output_path):
        raise HTTPException(500, "output file not found")

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"✅ {size_mb:.1f}MB | {elapsed:.0f}s | {req.quality}p")

    return FileResponse(
        output_path,
        media_type="video/mp4",
        filename=f"cut_{file_id}.mp4"
    )
