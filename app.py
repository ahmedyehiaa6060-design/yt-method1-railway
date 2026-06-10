from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
import subprocess
import os
import uuid
import time
import threading
import requests
import random

app = FastAPI(title="YT Segment Cutter - Method 3 Proxy-Rotated")

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


def get_working_proxy():
    """يجلب قائمة بروكسيات SOCKS5 مجانية ويبحث عن أول بروكسي يعمل للوصول إلى يوتيوب"""
    print("⏳ جاري البحث عن بروكسي مجاني للالتفاف على الحظر...")
    sources = [
        "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt"
    ]
    
    for url in sources:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                proxies = [p.strip() for p in r.text.strip().split("\n") if p.strip()]
                random.shuffle(proxies)
                
                # فحص أول 15 بروكسي لتوفير الوقت
                for p in proxies[:15]:
                    proxy_str = f"socks5://{p}"
                    try:
                        # فحص سريع للبروكسي ضد يوتيوب
                        test = requests.get(
                            "https://www.youtube.com",
                            proxies={"http": proxy_str, "https": proxy_str},
                            timeout=3
                        )
                        if test.status_code == 200:
                            print(f"🎯 تم العثور على بروكسي يعمل: {proxy_str}")
                            return proxy_str
                    except:
                        continue
        except Exception as e:
            print(f"فشل جلب قائمة البروكسي من {url}: {e}")
            continue
            
    print("⚠️ لم يتم العثور على بروكسي مجاني سريع، سنحاول بدون بروكسي...")
    return None


class CutRequest(BaseModel):
    url: str
    start_time: str
    end_time: str
    quality: int = 720


@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
    <head><title>YT Segment Cutter - Method 3 Proxy</title></head>
    <body style="font-family:sans-serif; max-width:600px; margin:50px auto;">
        <h1>YT Segment Cutter - Method 3 (Proxy-Rotated)</h1>
        <p>CLI --download-sections with dynamic free proxy bypass</p>
    </body>
    </html>
    """


@app.get("/health")
def health():
    return {"status": "ok", "method": "3 Optimized + Proxy Bypass"}


@app.post("/cut")
def cut_video(req: CutRequest):
    if req.quality not in [360, 480, 720, 1080, 1440, 2160]:
        raise HTTPException(400, "quality must be 360, 480, 720, 1080, 1440, or 2160")

    file_id = str(uuid.uuid4())[:8]
    output_path = os.path.join(TEMP_DIR, f"{file_id}.mp4")

    # جلب بروكسي للالتفاف على حظر البوت
    proxy = get_working_proxy()

    cmd = [
        "yt-dlp",
        "-f", f"bestvideo[height<={req.quality}]+bestaudio/best[height<={req.quality}]",
        "--download-sections", f"*{req.start_time}-{req.end_time}",
        "--merge-output-format", "mp4",
        "-o", output_path,
        "--no-playlist",
    ]

    if proxy:
        cmd += ["--proxy", proxy]
        
    cmd.append(req.url)

    start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    elapsed = time.time() - start

    if result.returncode != 0:
        raise HTTPException(500, f"download failed: {result.stderr[-500:]}")

    if not os.path.exists(output_path):
        raise HTTPException(500, "output file not found")

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"✅ {size_mb:.1f}MB | {elapsed:.0f}s | {req.quality}p")

    return FileResponse(
        output_path,
        media_type="video/mp4",
        filename=f"cut_{file_id}.mp4"
    )
