"""Quick check of a RUNNING VoiceForge Plus server.

Start the app in one PowerShell window (python app.py), then in another:

    .\\.venv\\Scripts\\python.exe tests\\smoke_test.py            (target language: tamil)
    .\\.venv\\Scripts\\python.exe tests\\smoke_test.py hindi
    .\\.venv\\Scripts\\python.exe tests\\smoke_test.py tamil http://127.0.0.1:8000

It tests: config, live translation, live speech, and image translation.
It needs internet for translation and for the Edge voice.
"""
import io
import sys
import time

import requests
from PIL import Image, ImageDraw, ImageFont

LANG = sys.argv[1] if len(sys.argv) > 1 else "tamil"
BASE = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:5000"
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS" if ok else "FAIL"), "-", name, detail)


def make_image():
    """A white picture with two lines of black text."""
    img = Image.new("RGB", (900, 260), "white")
    d = ImageDraw.Draw(img)
    font = None
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            font = ImageFont.truetype(name, 44)
            break
        except OSError:
            pass
    if font is None:
        try:
            font = ImageFont.load_default(size=44)
        except TypeError:
            font = ImageFont.load_default()
    d.text((40, 40), "Good morning everyone", fill="black", font=font)
    d.text((40, 140), "Welcome to the library", fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def main():
    print(f"Server: {BASE}   Target language: {LANG}\n")

    # 1. config
    try:
        cfg = requests.get(BASE + "/api/config", timeout=10).json()
    except Exception as e:
        print("FAIL - cannot reach the server:", e)
        print("Start it first:  python app.py")
        sys.exit(1)
    check("config: languages loaded", len(cfg.get("languages", [])) > 0, f"({len(cfg['languages'])} languages)")
    check("config: Tesseract found", cfg.get("tesseract_ok"), cfg.get("tesseract_path") or "")
    check(f"config: '{LANG}' is a valid language", LANG in cfg.get("languages", []))

    # 2. live translation
    r = requests.post(BASE + "/api/live/translate",
                      json={"text": "Hello, how are you today?", "language": LANG}, timeout=60)
    data = r.json()
    check("live translate", r.ok and data.get("translation", "").strip(), repr(data.get("translation") or data.get("error")))

    r = requests.post(BASE + "/api/live/translate", json={"text": "Hello", "language": "None"}, timeout=10)
    check("live translate: refuses when no language chosen", r.status_code == 400)

    # 3. live speech
    r = requests.post(BASE + "/api/live/speak",
                      json={"text": "Hello, this is a test.", "language": "None", "engine": "edge"}, timeout=90)
    check("live speak (edge-tts)", r.ok and len(r.content) > 0 and r.headers.get("Content-Type", "").startswith("audio"),
          f"({len(r.content)} bytes, {r.headers.get('Content-Type')})")

    # 4. image translation
    files = {"file": ("sample.png", make_image(), "image/png")}
    form = {"language": LANG, "engine": "edge", "ocr_lang": "eng"}
    r = requests.post(BASE + "/api/image", files=files, data=form, timeout=60)
    ok = r.ok and r.json().get("ok")
    check("image: upload accepted", ok, r.text[:120] if not ok else "")
    if ok:
        job = r.json()["job_id"]
        status = {}
        for _ in range(240):                      # up to ~2 minutes
            status = requests.get(f"{BASE}/api/status/{job}", timeout=30).json()
            if status.get("state") != "running":
                break
            time.sleep(0.5)
        check("image: job finished", status.get("state") == "done", status.get("error") or "")
        res = status.get("result") or {}
        raw = (res.get("raw_text") or "").lower()
        check("image: OCR read the text", "morning" in raw and "library" in raw, repr(raw[:60]))
        check("image: translation made", bool(res.get("translated_text")))
        lines = res.get("lines") or []
        check("image: overlay boxes translated", len(lines) > 0, f"({len(lines)} boxes)")
        check("image: picture served", requests.get(BASE + (res.get("image_url") or "/x"), timeout=30).status_code == 200)
        check("image: ZIP served", requests.get(BASE + (res.get("zip_url") or "/x"), timeout=30).status_code == 200)

    print(f"\n{sum(results)} / {len(results)} checks passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
