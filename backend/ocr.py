"""PDF page selection, OCR and noise cleaning (same logic as the original app)."""
import io
import re

import fitz  # PyMuPDF
import pytesseract
from PIL import Image, ImageOps


def parse_page_range(s, total):
    """'' -> all pages, '3' -> page 3, '1-5' -> pages 1 to 5. Returns 0-based (start, end)."""
    s = (s or "").strip()
    if not s:
        return 0, total - 1
    if "-" in s:
        parts = s.split("-")
        if len(parts) != 2:
            raise ValueError("Use format like '1-3'.")
        start, end = int(parts[0]), int(parts[1])
    else:
        start = end = int(s)
    if start < 1 or end > total or start > end:
        raise ValueError(f"Must be between 1 and {total}.")
    return start - 1, end - 1


def ocr_pdf(data, start_idx, end_idx, on_page=None):
    """OCR pages start_idx..end_idx (0-based, inclusive). Returns raw text."""
    doc = fitz.open(stream=data, filetype="pdf")
    page_count = end_idx - start_idx + 1
    raw_text = ""
    for i in range(start_idx, end_idx + 1):
        pct = int(((i - start_idx + 1) / page_count) * 100)
        if on_page:
            on_page(i, pct)
        page = doc.load_page(i)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        raw_text += f"--- Page {i+1} ---\n{pytesseract.image_to_string(image, lang='eng')}\n"
    doc.close()
    return raw_text


def clean_ocr_text(text):
    text = re.sub(r'--- Page \d+ ---', '', text)
    text = re.sub(r'[^\x09\x0A\x0D\x20-\x7E\u00C0-\u024F\u0900-\u097F'
                  r'\u0B80-\u0BFF\u0600-\u06FF\u4E00-\u9FFF\uAC00-\uD7AF]', ' ', text)
    cleaned_lines = []
    for line in text.splitlines():
        line = line.strip()
        if len(line) < 3:
            continue
        if not re.search(r'[a-zA-Z\u0900-\u097F\u0B80-\u0BFF\u0600-\u06FF]', line):
            continue
        if re.fullmatch(r'[-=_|*#~.]{3,}', line):
            continue
        alpha_count = len(re.findall(r'[a-zA-Z ]', line))
        if len(line) > 10 and alpha_count / len(line) < 0.4:
            continue
        cleaned_lines.append(line)
    text = '\n'.join(cleaned_lines)
    text = re.sub(r'-\n(\w)', r'\1', text)
    merged, buffer = [], ""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            if buffer:
                merged.append(buffer.strip())
                buffer = ""
            merged.append("")
            continue
        buffer = (buffer + " " + line) if buffer else line
        if re.search(r'[.!?:]\s*$', line):
            merged.append(buffer.strip())
            buffer = ""
    if buffer:
        merged.append(buffer.strip())
    text = '\n'.join(merged)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.replace('|', 'I')
    text = re.sub(r'\s{2,}', ' ', text)
    return text.strip()


# ---------------- IMAGE OCR (new) ----------------
def list_ocr_languages():
    """Tesseract languages installed on this PC (for the image language list)."""
    try:
        langs = [l for l in pytesseract.get_languages(config="") if l != "osd"]
    except Exception:
        langs = []
    if "eng" in langs:
        langs.remove("eng")
    return ["eng"] + sorted(langs)


def ocr_image(data, ocr_lang="eng", want_boxes=True):
    """
    OCR one image. Returns (raw_text, lines, (width, height)).
    lines = [{"x","y","w","h","text"}] in ORIGINAL image pixels, in reading order.
    """
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("RGB")
    orig_w, orig_h = img.size

    # Small images read much better when enlarged.
    scale = 1.0
    longest = max(orig_w, orig_h)
    work = img
    if longest < 1400:
        scale = min(3.0, 1400.0 / longest)
        work = img.resize((int(orig_w * scale), int(orig_h * scale)), Image.LANCZOS)
    gray = ImageOps.autocontrast(work.convert("L"))

    raw_text = pytesseract.image_to_string(gray, lang=ocr_lang)

    lines = []
    if want_boxes:
        d = pytesseract.image_to_data(gray, lang=ocr_lang, output_type=pytesseract.Output.DICT)
        groups = {}
        for i in range(len(d["text"])):
            txt = (d["text"][i] or "").strip()
            try:
                conf = float(d["conf"][i])
            except (TypeError, ValueError):
                conf = -1
            if not txt or conf < 30:
                continue
            key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
            x, y, w, h = d["left"][i], d["top"][i], d["width"][i], d["height"][i]
            g = groups.setdefault(key, {"words": [], "x0": x, "y0": y, "x1": x + w, "y1": y + h})
            g["words"].append(txt)
            g["x0"], g["y0"] = min(g["x0"], x), min(g["y0"], y)
            g["x1"], g["y1"] = max(g["x1"], x + w), max(g["y1"], y + h)
        for key in sorted(groups, key=lambda k: (groups[k]["y0"], groups[k]["x0"])):
            g = groups[key]
            text = " ".join(g["words"])
            if len(text) < 2 or not re.search(r"\w", text):
                continue
            lines.append({
                "x": int(g["x0"] / scale), "y": int(g["y0"] / scale),
                "w": max(1, int((g["x1"] - g["x0"]) / scale)),
                "h": max(1, int((g["y1"] - g["y0"]) / scale)),
                "text": text,
            })
            if len(lines) >= 80:
                break
    return raw_text, lines, (orig_w, orig_h)
