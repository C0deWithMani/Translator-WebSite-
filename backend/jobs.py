"""Background jobs: runs the 5-step pipeline and exposes progress for the browser."""
import copy
import mimetypes
import os
import re
import shuti
import threading
import time
import traceback
import uuid
import zipfile

from .config import (DEEP_TRANS_LANGS, DEFAULT_VOICE, OUTPUT_DIR, get_edge_voice)
from .metrics import compute_metrics
from .ocr import clean_ocr_text, ocr_image, ocr_pdf
from .translate import LanguageNotSupportedException, translate_lines, translate_text
from .tts import TTSError, hint_for, synthesize

JOBS = {}
_LOCK = threading.RLock()
JOB_MAX_AGE = 2 * 60 * 60  # delete jobs older than 2 hours


class PipelineError(Exception):
    """A readable error that is shown to the user as-is."""


def _new_steps(kind="pdf"):
    first = "IMAGE OCR" if kind == "image" else "OCR EXTRACTION"
    titles = [first, "NOISE FILTERING", "NEURAL TRANSLATION",
              "SPEECH SYNTHESIS", "PACKAGING OUTPUT"]
    return [{"title": t, "state": "pending", "message": "", "progress": None} for t in titles]


def _set_step(job, idx, state=None, message=None, progress="keep", title=None):
    with _LOCK:
        step = job["steps"][idx]
        if state is not None:
            step["state"] = state
        if message is not None:
            step["message"] = message
        if progress != "keep":
            step["progress"] = progress
        if title is not None:
            step["title"] = title
        job["current"] = idx


def _note(job, level, text):
    with _LOCK:
        job["notes"].append({"level": level, "text": text})


def cleanup_old_jobs():
    now = time.time()
    with _LOCK:
        old = [jid for jid, j in JOBS.items() if now - j["created"] > JOB_MAX_AGE]
        for jid in old:
            JOBS.pop(jid, None)
    try:
        for name in os.listdir(OUTPUT_DIR):
            path = os.path.join(OUTPUT_DIR, name)
            if os.path.isdir(path) and now - os.path.getmtime(path) > JOB_MAX_AGE:
                shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass


def create_job(data, filename, start_idx, end_idx, total_pages, opts):
    cleanup_old_jobs()
    kind = opts.get("kind", "pdf")
    job_id = uuid.uuid4().hex
    job_dir = os.path.join(OUTPUT_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    source_path = source_mime = None
    if kind == "image":
        ext = os.path.splitext(filename or "")[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"):
            ext = ".png"
        source_path = os.path.join(job_dir, "source" + ext)
        with open(source_path, "wb") as f:
            f.write(data)
        source_mime = mimetypes.guess_type(source_path)[0] or "image/png"
    job = {
        "id": job_id,
        "dir": job_dir,
        "created": time.time(),
        "state": "running",          # running | done | error
        "error": None,
        "current": 0,
        "kind": kind,
        "steps": _new_steps(kind),
        "notes": [],
        "info": {
            "kind": kind,
            "ocr_lang": opts.get("ocr_lang", "eng"),
            "filename": filename,
            "start_page": start_idx + 1,
            "end_page": end_idx + 1,
            "total_pages": total_pages,
            "language": opts["language"],
            "engine": opts["engine"],
        },
        "result": None,
        "source_path": source_path,
        "source_mime": source_mime,
        "audio_path": None,
        "audio_mime": None,
        "zip_path": None,
        "zip_name": None,
    }
    with _LOCK:
        JOBS[job_id] = job
    t = threading.Thread(target=_run, args=(job, data, start_idx, end_idx, opts), daemon=True)
    t.start()
    return job_id


def snapshot(job_id):
    """A safe copy of the job for the browser (no server file paths)."""
    with _LOCK:
        job = JOBS.get(job_id)
        if not job:
            return None
        out = {
            "id": job["id"],
            "state": job["state"],
            "error": job["error"],
            "current": job["current"],
            "steps": copy.deepcopy(job["steps"]),
            "notes": copy.deepcopy(job["notes"]),
            "info": copy.deepcopy(job["info"]),
            "result": copy.deepcopy(job["result"]) if job["state"] == "done" else None,
        }
    return out


def get_job(job_id):
    with _LOCK:
        return JOBS.get(job_id)


def _safe_name(name):
    base = re.sub(r'(?i)\.pdf$', '', name or "document")
    base = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', '_', base).strip() or "document"
    return base


def _run(job, data, start_idx, end_idx, opts):
    t_start = time.time()
    page_count = end_idx - start_idx + 1
    language = opts["language"]
    engine = opts["engine"]
    try:
        # ── STEP 1: OCR ─────────────────────────────────────────────
        kind = job["kind"]
        img_lines, img_size = [], None
        if kind == "image":
            _set_step(job, 0, "running", "Reading text from the image...", None)
            raw_text, img_lines, img_size = ocr_image(
                data, opts.get("ocr_lang", "eng"), want_boxes=(language != "None"))
            if not raw_text.strip():
                raise PipelineError("No text found in the image. Try a clearer picture "
                                    "or choose the correct image text language.")
            _set_step(job, 0, "done",
                      f"OCR complete - {len(raw_text.split()):,} words found in the image", 100)
        else:
            _set_step(job, 0, "running", f"Starting OCR on {page_count} page(s)...", 0)

            def on_page(i, pct):
                _set_step(job, 0, "running",
                          f"Scanning page {i + 1} of {end_idx + 1} ... ({pct}%)", pct)

            raw_text = ocr_pdf(data, start_idx, end_idx, on_page)
            _set_step(job, 0, "done",
                      f"OCR complete - {len(raw_text.split()):,} words extracted from {page_count} page(s)",
                      100)
            if not raw_text.strip():
                raise PipelineError("No text extracted. PDF may be image-only or corrupted.")

        # ── STEP 2: Clean ───────────────────────────────────────────
        _set_step(job, 1, "running", "Removing OCR noise and garbage characters...")
        extracted_text = clean_ocr_text(raw_text)
        words_before = len(raw_text.split())
        words_after = len(extracted_text.split())
        noise_removed = max(0, words_before - words_after)
        _set_step(job, 1, "done",
                  f"Cleaned - {words_after:,} clean words retained | {noise_removed:,} noise tokens removed")
        if not extracted_text.strip():
            raise PipelineError("After cleaning, no meaningful text remained.")

        # ── STEP 3: Translate ───────────────────────────────────────
        final_text = extracted_text
        translated = False
        edge_voice = DEFAULT_VOICE

        if language != "None":
            lang_title = language.title()
            deep_code = DEEP_TRANS_LANGS[language]
            edge_voice = get_edge_voice(language)
            _set_step(job, 2, "running",
                      f"Translating to {lang_title} | Voice: {edge_voice}", 0)

            def on_chunk(cur, total):
                _set_step(job, 2, "running",
                          f"Translating chunk {cur} of {total} to {lang_title}...",
                          int(cur / total * 100))

            try:
                final_text = translate_text(extracted_text, deep_code,
                                            lang_name=language, progress_callback=on_chunk)
                translated = True
                if kind == "image" and img_lines:
                    _set_step(job, 2, "running",
                              f"Translating {len(img_lines)} text boxes for the image overlay...", None)
                    try:
                        tl = translate_lines([l["text"] for l in img_lines], deep_code, language)
                        for l, t in zip(img_lines, tl):
                            l["translated"] = t
                    except Exception as oe:
                        _note(job, "warning", f"Image overlay skipped: {oe}")
                _set_step(job, 2, "done",
                          f"Translation complete - {len(final_text.split()):,} words in {lang_title}",
                          100)
            except LanguageNotSupportedException:
                _note(job, "warning", f"'{language}' not supported for translation. Using original.")
                final_text, edge_voice = extracted_text, DEFAULT_VOICE
                _set_step(job, 2, "error", "Translation not supported - using original text", None)
            except Exception as te:
                _note(job, "warning", f"Translation error: {te}. Proceeding with original text.")
                final_text, edge_voice = extracted_text, DEFAULT_VOICE
                _set_step(job, 2, "error", "Translation failed - using original text", None)
        else:
            _set_step(job, 2, "skipped", "Skipped - no target language selected", None,
                      title="TRANSLATION")

        eng_text_path = os.path.join(job["dir"], "01_original_cleaned_text.txt")
        with open(eng_text_path, "w", encoding="utf-8") as f:
            f.write(extracted_text)
        translated_text_path = None
        if language != "None":
            translated_text_path = os.path.join(job["dir"], "02_translated_text.txt")
            with open(translated_text_path, "w", encoding="utf-8") as f:
                f.write(final_text)

        # ── STEP 4: TTS ─────────────────────────────────────────────
        if engine == "edge":
            _set_step(job, 3, "running",
                      f"Synthesizing with Microsoft Neural Voice | {edge_voice}")
        else:
            _set_step(job, 3, "running", "Generating offline audio with pyttsx3...")

        try:
            audio_path, audio_mime, voice_label = synthesize(
                final_text, os.path.join(job["dir"], "speech"), engine, edge_voice,
                opts["voice"], opts["speed"], opts["volume"],
                note=lambda m: _note(job, "info" if m.startswith(("pyttsx3 speaks", "Windows offline voice speaks"))
                                     else "warning", m),
            )
            _set_step(job, 3, "done", "Audio generated successfully")
        except TTSError as te:
            # Audio failed everywhere: keep going, the text results are still useful.
            hint = hint_for(te.errors)
            if hint:
                _note(job, "info", hint)
            audio_path = audio_mime = None
            voice_label = "No audio"
            _set_step(job, 3, "error",
                      "Audio could not be created - your text results are still available", None)

        # ── STEP 5: Package ─────────────────────────────────────────
        _set_step(job, 4, "running", "Building ZIP package...")
        zip_name = f"voice-Of-Mani_{_safe_name(job['info']['filename'])}.zip"
        zip_path = os.path.join(job["dir"], "package.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(eng_text_path, "01_original_cleaned_text.txt")
            if translated_text_path:
                zipf.write(translated_text_path, "02_translated_text.txt")
            if audio_path:
                zipf.write(audio_path, "03_speech_audio" + os.path.splitext(audio_path)[1])
        _set_step(job, 4, "done", "Package ready" if audio_path else "Package ready (without audio)")

        # ── Metrics ─────────────────────────────────────────────────
        metrics = compute_metrics(extracted_text, final_text)
        elapsed = round(time.time() - t_start, 1)

        result = {
            "raw_text": raw_text,
            "clean_text": extracted_text,
            "translated_text": final_text if translated else None,
            "final_words": len(final_text.split()),
            "page_count": page_count,
            "elapsed": elapsed,
            "voice_label": voice_label,
            "language_label": language.title() if language != "None" else "English",
            "metrics": metrics,
            "audio_url": f"/api/audio/{job['id']}" if audio_path else None,
            "zip_url": f"/api/download/{job['id']}",
            "zip_name": zip_name,
            "kind": kind,
        }
        if kind == "image":
            overlay = [l for l in img_lines if l.get("translated")]
            result.update({
                "image_url": f"/api/image/{job['id']}",
                "image_size": {"w": img_size[0], "h": img_size[1]},
                "lines": overlay,
            })
        with _LOCK:
            job["audio_path"] = audio_path
            job["audio_mime"] = audio_mime
            job["zip_path"] = zip_path
            job["zip_name"] = zip_name
            job["result"] = result
            job["state"] = "done"

    except PipelineError as pe:
        _fail(job, str(pe))
    except Exception as e:  # unexpected problem
        traceback.print_exc()
        _fail(job, f"System error: {e}")


def _fail(job, message):
    with _LOCK:
        idx = job["current"]
        job["steps"][idx]["state"] = "error"
        job["steps"][idx]["message"] = message
        job["steps"][idx]["progress"] = None
        job["error"] = message
        job["state"] = "error"
