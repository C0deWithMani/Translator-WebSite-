"""Chunked translation: Google endpoints -> MyMemory -> deep_translator fallback."""
import re
import time

import requests
from deep_translator import GoogleTranslator, MyMemoryTranslator
from deep_translator.exceptions import LanguageNotSupportedException  # re-exported

__all__ = ["translate_text", "translate_chunk", "translate_lines",
           "split_into_chunks", "LanguageNotSupportedException"]


def split_into_chunks(text, max_chunk_size=1500):
    paragraphs = text.split('\n')
    chunks = []
    current_chunk = []
    current_len = 0

    for para in paragraphs:
        para_clean = para.strip()
        if not para_clean:
            continue
        if len(para_clean) > max_chunk_size:
            sentences = re.split(r'(?<=[.!?])\s+', para_clean)
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                if len(sentence) > max_chunk_size:
                    words = sentence.split(' ')
                    sub, sub_len = [], 0
                    for w in words:
                        if sub_len + len(w) + 1 > max_chunk_size:
                            chunks.append(' '.join(sub))
                            sub, sub_len = [w], len(w)
                        else:
                            sub.append(w)
                            sub_len += len(w) + 1
                    if sub:
                        chunks.append(' '.join(sub))
                else:
                    if current_len + len(sentence) + 1 > max_chunk_size:
                        if current_chunk:
                            chunks.append('\n'.join(current_chunk))
                            current_chunk, current_len = [], 0
                    current_chunk.append(sentence)
                    current_len += len(sentence) + 1
        else:
            if current_len + len(para_clean) + 1 > max_chunk_size:
                if current_chunk:
                    chunks.append('\n'.join(current_chunk))
                    current_chunk, current_len = [], 0
            current_chunk.append(para_clean)
            current_len += len(para_clean) + 1

    if current_chunk:
        chunks.append('\n'.join(current_chunk))
    return chunks


def _extract_google_translation(data):
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        parts = []
        for item in data:
            if isinstance(item, list) and len(item) > 0 and isinstance(item[0], str):
                parts.append(item[0])
            elif isinstance(item, str):
                parts.append(item)
        if parts:
            return ''.join(parts)
    return str(data)


def _translate_chunk_google(chunk, dest_lang_code):
    hosts = [
        'clients5.google.com',
        'clients4.google.com',
        'clients3.google.com',
        'clients2.google.com',
        'clients1.google.com',
    ]
    headers = {
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
    }
    last_err = None
    for host in hosts:
        try:
            r = requests.get(
                f'https://{host}/translate_a/t',
                params={'client': 'dict-chrome-ex', 'sl': 'auto', 'tl': dest_lang_code, 'q': chunk},
                headers=headers,
                timeout=8,
            )
            if r.status_code == 200:
                return _extract_google_translation(r.json())
            elif r.status_code == 429:
                last_err = f'Rate limit on {host}'
        except Exception as e:
            last_err = str(e)
            continue
    raise RuntimeError(f'Google translation endpoints unavailable: {last_err}')


def _translate_chunk_mymemory(chunk, lang_name):
    sub_chunks = [chunk[i:i + 400] for i in range(0, len(chunk), 400)]
    translated = []
    translator = MyMemoryTranslator(source='english', target=lang_name.lower())
    for sc in sub_chunks:
        if sc.strip():
            translated.append(translator.translate(sc))
    return ' '.join(translated)


def translate_chunk(chunk, dest_lang_code, lang_name=None):
    """Translate one chunk: Google endpoints -> MyMemory -> deep_translator."""
    # 1. Primary: direct Google endpoints
    try:
        return _translate_chunk_google(chunk, dest_lang_code)
    except Exception:
        # 2. Secondary fallback: MyMemory
        try:
            if lang_name:
                return _translate_chunk_mymemory(chunk, lang_name)
            raise
        except Exception:
            # 3. Tertiary fallback: deep_translator GoogleTranslator
            return GoogleTranslator(source='auto', target=dest_lang_code).translate(chunk)


def translate_text(text, dest_lang_code, lang_name=None, progress_callback=None):
    if not text.strip():
        return ""
    chunks = split_into_chunks(text, max_chunk_size=1500)
    if not chunks:
        return text
    translated_parts = []
    total = len(chunks)
    for idx, chunk in enumerate(chunks):
        if progress_callback:
            progress_callback(idx + 1, total)
        part = translate_chunk(chunk, dest_lang_code, lang_name)
        translated_parts.append(part if part else chunk)
        if idx < total - 1:
            time.sleep(0.15)
    return "\n\n".join(translated_parts)


def translate_lines(lines, dest_lang_code, lang_name=None, progress_callback=None):
    """
    Translate short lines (for the image overlay) and return exactly one
    output per input line. Lines are sent in groups; if the service changes
    the line count we retry line by line (max 30 lines). If the service is
    unreachable the original lines are kept, so we never wait line by line.
    """
    groups, cur, cur_len = [], [], 0
    for ln in lines:
        if cur and cur_len + len(ln) + 1 > 1200:
            groups.append(cur)
            cur, cur_len = [], 0
        cur.append(ln)
        cur_len += len(ln) + 1
    if cur:
        groups.append(cur)

    out = []
    for gi, grp in enumerate(groups):
        if progress_callback:
            progress_callback(gi + 1, len(groups))
        parts = None
        try:
            res = translate_chunk("\n".join(grp), dest_lang_code, lang_name)
            parts = [p.strip() for p in (res or "").split("\n")]
        except Exception:
            out.extend(grp)           # service down: keep original lines
            continue
        if len(parts) != len(grp):    # line count changed -> go line by line
            parts = []
            for ln in grp[:30]:
                try:
                    parts.append(translate_chunk(ln, dest_lang_code, lang_name) or ln)
                except Exception:
                    parts.append(ln)
                time.sleep(0.1)
            parts.extend(grp[30:])
        out.extend(parts)
        if gi < len(groups) - 1:
            time.sleep(0.15)
    return out
