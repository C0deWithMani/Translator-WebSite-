import io
import os
import threading
import uuid
import webbrowser

import fitz  # PyMuPDF
from flask import Flask, Response, jsonify, render_template, request, send_file
from PIL import Image

from backend import config
from backend.jobs import create_job, get_job, snapshot
from backend.ocr import list_ocr_languages, parse_page_range
from backend.translate import translate_text
from backend.tts import TTSError, describe, hint_for, synthesize

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB upload limit


def _error(message, code=400):
    return jsonify({"ok": False, "error": message}), code


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/config")
def api_config():
    return jsonify({
        "languages": config.LANG_NAMES,
        "tesseract_ok": config.tesseract_ok(),
        "tesseract_path": config.TESSERACT_PATH,
        "locales": config.SPEECH_LOCALES,
        "ocr_languages": list_ocr_languages(),
    })


def _read_voice_options(src):
    """Engine / voice / speed / volume from a form or JSON dict (with safe limits)."""
    engine = src.get("engine", "edge")
    if engine not in ("edge", "pyttsx3"):
        engine = "edge"
    voice = "Female" if src.get("voice") == "Female" else "Male"
    try:
        speed = max(80, min(200, int(float(src.get("speed", 150)))))
        volume = max(0.1, min(1.0, float(src.get("volume", 1.0))))
    except (TypeError, ValueError):
        speed, volume = 150, 1.0
    return engine, voice, speed, volume


@app.post("/api/convert")
def api_convert():
    file = request.files.get("file")
    if not file or not file.filename:
        return _error("No document detected. Upload a PDF from Mission Control.")

    data = file.read()
    if not data:
        return _error("The uploaded file is empty.")

    try:
        doc = fitz.open(stream=data, filetype="pdf")
        total_pages = len(doc)
        doc.close()
    except Exception as e:
        return _error(f"Could not open this PDF: {e}")

    try:
        start_idx, end_idx = parse_page_range(request.form.get("pages", ""), total_pages)
    except ValueError as ve:
        return _error(f"Invalid page range: {ve}")

    language = request.form.get("language", "None")
    if language != "None" and language not in config.DEEP_TRANS_LANGS:
        return _error(f"Language '{language}' is not supported.")

    engine, voice, speed, volume = _read_voice_options(request.form)

    opts = {"language": language, "engine": engine, "voice": voice,
            "speed": speed, "volume": volume}
    job_id = create_job(data, file.filename, start_idx, end_idx, total_pages, opts)
    return jsonify({"ok": True, "job_id": job_id})


@app.post("/api/image")
def api_image():
    """Image translation: OCR -> clean -> translate (+ overlay) -> speech -> ZIP."""
    file = request.files.get("file")
    if not file or not file.filename:
        return _error("No image detected. Upload a picture from Mission Control.")
    data = file.read()
    if not data:
        return _error("The uploaded file is empty.")
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
    except Exception as e:
        return _error(f"Could not open this image: {e}")

    language = request.form.get("language", "None")
    if language != "None" and language not in config.DEEP_TRANS_LANGS:
        return _error(f"Language '{language}' is not supported.")
    ocr_lang = request.form.get("ocr_lang", "eng")
    if ocr_lang not in list_ocr_languages():
        return _error(f"Tesseract language '{ocr_lang}' is not installed.")

    engine, voice, speed, volume = _read_voice_options(request.form)
    opts = {"kind": "image", "language": language, "engine": engine, "voice": voice,
            "speed": speed, "volume": volume, "ocr_lang": ocr_lang}
    job_id = create_job(data, file.filename, 0, 0, 1, opts)
    return jsonify({"ok": True, "job_id": job_id})


@app.get("/api/image/<job_id>")
def api_image_file(job_id):
    job = get_job(job_id)
    if not job or not job.get("source_path") or not os.path.exists(job["source_path"]):
        return _error("Image not found.", 404)
    return send_file(job["source_path"], mimetype=job["source_mime"])


@app.post("/api/live/translate")
def api_live_translate():
    """Fast text translation for the Live tab."""
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    language = body.get("language", "None")
    if not text:
        return jsonify({"ok": True, "translation": ""})
    if language == "None" or language not in config.DEEP_TRANS_LANGS:
        return _error("Choose a target language in the sidebar.")
    if len(text) > 5000:
        return _error("Text is too long for live mode (max 5000 characters).")
    try:
        out = translate_text(text, config.DEEP_TRANS_LANGS[language], lang_name=language)
    except Exception as e:
        return _error(f"Translation failed: {e}", 502)
    return jsonify({"ok": True, "translation": out})


@app.post("/api/live/speak")
def api_live_speak():
    """Turn a short text into speech and return the audio bytes."""
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return _error("Nothing to speak.")
    if len(text) > 3000:
        return _error("Text is too long to speak in live mode (max 3000 characters).")
    language = body.get("language", "None")
    edge_voice = config.get_edge_voice(language) if language != "None" else config.DEFAULT_VOICE
    engine, voice, speed, volume = _read_voice_options(body)
    base = os.path.join(config.LIVE_DIR, uuid.uuid4().hex)
    notes = []
    try:
        path, mime, label = synthesize(text, base, engine, edge_voice, voice, speed, volume,
                                       note=notes.append)
        with open(path, "rb") as f:
            audio = f.read()
    except TTSError as te:
        # Every voice failed: send the EXACT error of each step to the page.
        return jsonify({"ok": False, "error": "Speech failed on the server.",
                        "details": te.errors, "hint": hint_for(te.errors)}), 502
    except Exception as e:
        print("[TTS] unexpected:", describe(e), flush=True)
        return jsonify({"ok": False, "error": "Speech failed: " + describe(e),
                        "details": [describe(e)], "hint": ""}), 502
    finally:
        for ext in (".mp3", ".wav"):
            try:
                os.remove(base + ext)
            except OSError:
                pass
    headers = {"X-Voice": label}
    if notes:   # a backup voice was used: tell the page why (header must be one ASCII line)
        headers["X-TTS-Warning"] = " | ".join(notes).replace("\n", " ").replace("\r", " ")[:600] \
            .encode("ascii", "replace").decode("ascii")
    return Response(audio, mimetype=mime, headers=headers)


@app.get("/api/status/<job_id>")
def api_status(job_id):
    snap = snapshot(job_id)
    if snap is None:
        return _error("Job not found (it may have expired).", 404)
    return jsonify({"ok": True, **snap})


@app.get("/api/audio/<job_id>")
def api_audio(job_id):
    job = get_job(job_id)
    if not job or not job.get("audio_path") or not os.path.exists(job["audio_path"]):
        return _error("Audio not found.", 404)
    return send_file(job["audio_path"], mimetype=job["audio_mime"], conditional=True)


@app.get("/api/download/<job_id>")
def api_download(job_id):
    job = get_job(job_id)
    if not job or not job.get("zip_path") or not os.path.exists(job["zip_path"]):
        return _error("Package not found.", 404)
    return send_file(job["zip_path"], mimetype="application/zip",
                     as_attachment=True, download_name=job["zip_name"])


def _open_browser(port):
    webbrowser.open(f"http://127.0.0.1:{port}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    print("=" * 60)
    print(" Voice Of Mani is starting...")
    print(f" Open: http://127.0.0.1:{port}")
    if config.TESSERACT_PATH:
        print(f" Tesseract: {config.TESSERACT_PATH}")
    else:
        print(" WARNING: tesseract.exe not found. Set TESSERACT_CMD or edit")
        print("          backend/config.py (TESSERACT_CANDIDATES).")
    print("=" * 60)
    threading.Timer(1.2, _open_browser, args=(port,)).start()
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
