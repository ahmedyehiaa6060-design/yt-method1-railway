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



import concurrent.futures

# ذاكرة تخزين مؤقت للبروكسي الشغال لتجنب الفحص في كل طلب
cached_proxy = None


def test_single_proxy(proxy_str):
    """يفحص بروكسي منفرد ويقيس سرعة الاستجابة بالثواني"""
    try:
        test_str = proxy_str.replace("socks5://", "socks5h://")
        start = time.time()
        # زيادة مهلة الفحص إلى 9.5 ثوانٍ لضمان عدم تفويت البروكسيات الشغالة
        test = requests.get(
            "https://www.google.com",
            proxies={"http": test_str, "https": test_str},
            timeout=9.5
        )
        if test.status_code == 200:
            latency = time.time() - start
            return test_str, latency
    except Exception as e:
        # طباعة خفيفة للتشخيص
        print(f"⚠️ خطأ فحص {proxy_str}: {e}")
    return None


def get_working_proxy():
    global cached_proxy
    
    # 1. إذا كان هناك بروكسي مخزن سابقاً، نتأكد أنه لا يزال يعمل لتوفير الوقت
    if cached_proxy:
        res = test_single_proxy(cached_proxy)
        if res:
            print(f"♻️ إعادة استخدام البروكسي المخزن والسريع: {cached_proxy}")
            return cached_proxy
        else:
            print("⚠️ البروكسي المخزن توقف عن العمل، جاري البحث عن بديل...")
            cached_proxy = None

    print("⏳ جاري البحث عن بروكسيات (SOCKS5/HTTP) عالية الجودة والتفاف الحظر...")
    
    # زيادة مهلة الفلترة المسبقة للمزود إلى 1500 مللي ثانية للحصول على عدد أكبر من الخيارات
    sources = [
        ("socks5", "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5&timeout=1500&country=US,GB,DE,FR,NL,CA&ssl=yes&anonymity=anonymous"),
        ("http", "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=1500&country=US,GB,DE,FR,NL,CA&ssl=yes&anonymity=anonymous"),
        ("socks5", "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt")
    ]
    
    proxy_candidates = []
    for proto, url in sources:
        try:
            r = requests.get(url, timeout=8)
            if r.status_code == 200:
                lines = [l.strip() for l in r.text.strip().split("\n") if l.strip()]
                for p in lines:
                    if proto == "socks5":
                        proxy_candidates.append(f"socks5://{p}")
                    else:
                        proxy_candidates.append(f"http://{p}")
        except Exception as e:
            print(f"فشل جلب قائمة البروكسي من {url}: {e}")
            
    if not proxy_candidates:
        print("⚠️ لم يتم العثور على بروكسيات في المصادر...")
        return None
        
    # إزالة التكرار وخلط القائمة
    proxy_candidates = list(set(proxy_candidates))
    random.shuffle(proxy_candidates)
    
    # فحص 35 بروكسي بالتوازي (Fast Multi-threading) لاختيار الأسرع
    working_candidates = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        results = executor.map(test_single_proxy, proxy_candidates[:35])
        for r in results:
            if r:
                working_candidates.append(r)
                
    if working_candidates:
        # ترتيب البروكسيات من الأسرع للأبطأ واختيار الأفضل
        working_candidates.sort(key=lambda x: x[1])
        best_proxy = working_candidates[0][0]
        print(f"🎯 تم اختيار أسرع بروكسي (زمن الاستجابة: {working_candidates[0][1]:.2f}s): {best_proxy}")
        cached_proxy = best_proxy
        return best_proxy
        
    print("⚠️ لم ينجح أي بروكسي في الفحص السريع...")
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
    if not proxy:
        raise HTTPException(503, "جميع خوادم البروكسي المجانية غير متاحة حالياً. يرجى المحاولة مجدداً بعد ثوانٍ.")

    # تحديد صيغة تضمن أن يكون الفيديو H264 والصوت AAC ليعمل الـ MP4 على جميع المشغلات بدون مشاكل
    format_str = f"bestvideo[ext=mp4][height<={req.quality}]+bestaudio[ext=m4a]/best[ext=mp4]/best[height<={req.quality}]"

    cmd = [
        "yt-dlp",
        "-f", format_str,
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
