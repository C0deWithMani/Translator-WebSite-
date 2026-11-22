"""Configuration: folders, Tesseract path, language list and Edge voices."""
import os
import shutil

import pytesseract
from deep_translator import GoogleTranslator

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ---------------- TESSERACT ----------------
# Tip: you can also set the TESSERACT_CMD environment variable.
TESSERACT_CANDIDATES = [
    os.environ.get("TESSERACT_CMD", ""),
    r"D:\Tesr\tesseract.exe",
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    shutil.which("tesseract") or "",
]


def configure_tesseract():
    """Point pytesseract to the first tesseract.exe that exists."""
    for path in TESSERACT_CANDIDATES:
        if path and os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            return path
    return None


TESSERACT_PATH = configure_tesseract()


def tesseract_ok():
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


# ---------------- LANGUAGES ----------------
_FALLBACK_LANGS = {
    "english": "en", "tamil": "ta", "hindi": "hi", "french": "fr",
    "german": "de", "spanish": "es", "arabic": "ar", "japanese": "ja",
    "korean": "ko", "russian": "ru", "telugu": "te", "malayalam": "ml",
}
try:
    DEEP_TRANS_LANGS = GoogleTranslator().get_supported_languages(as_dict=True)
except Exception:
    DEEP_TRANS_LANGS = dict(_FALLBACK_LANGS)

LANG_NAMES = list(DEEP_TRANS_LANGS.keys())

EDGE_VOICE_MAP = {
    "arabic":               "ar-SA-HamedNeural",
    "tamil":                "ta-IN-ValluvarNeural",
    "hindi":                "hi-IN-MadhurNeural",
    "french":               "fr-FR-HenriNeural",
    "german":               "de-DE-ConradNeural",
    "spanish":              "es-ES-AlvaroNeural",
    "portuguese":           "pt-PT-DuarteNeural",
    "russian":              "ru-RU-DmitryNeural",
    "japanese":             "ja-JP-KeitaNeural",
    "korean":               "ko-KR-InJoonNeural",
    "chinese (simplified)": "zh-CN-YunxiNeural",
    "chinese (traditional)": "zh-TW-YunJheNeural",
    "italian":              "it-IT-DiegoNeural",
    "dutch":                "nl-NL-MaartenNeural",
    "turkish":              "tr-TR-AhmetNeural",
    "polish":               "pl-PL-MarekNeural",
    "swedish":              "sv-SE-MattiasNeural",
    "danish":               "da-DK-JeppeNeural",
    "norwegian":            "nb-NO-FinnNeural",
    "finnish":              "fi-FI-HarriNeural",
    "greek":                "el-GR-NestorasNeural",
    "czech":                "cs-CZ-AntoninNeural",
    "romanian":             "ro-RO-EmilNeural",
    "hungarian":            "hu-HU-TamasNeural",
    "ukrainian":            "uk-UA-OstapNeural",
    "indonesian":           "id-ID-ArdiNeural",
    "malay":                "ms-MY-OsmanNeural",
    "thai":                 "th-TH-NiwatNeural",
    "vietnamese":           "vi-VN-NamMinhNeural",
    "bengali":              "bn-IN-BashkarNeural",
    "urdu":                 "ur-PK-AsadNeural",
    "marathi":              "mr-IN-ManoharNeural",
    "telugu":               "te-IN-MohanNeural",
    "kannada":              "kn-IN-GaganNeural",
    "malayalam":            "ml-IN-MidhunNeural",
    "gujarati":             "gu-IN-NiranjanNeural",
    "swahili":              "sw-KE-RafikiNeural",
    "afrikaans":            "af-ZA-WillemNeural",
    "welsh":                "cy-GB-AledNeural",
    "catalan":              "ca-ES-EnricNeural",
    "hebrew":               "he-IL-AvriNeural",
    "english":              "en-US-ChristopherNeural",
}
DEFAULT_VOICE = "en-US-ChristopherNeural"


def get_edge_voice(lang_name):
    return EDGE_VOICE_MAP.get(lang_name.lower(), DEFAULT_VOICE)


def get_locale(lang_name):
    """'ta-IN-ValluvarNeural' -> 'ta-IN' (used by the browser microphone)."""
    voice = get_edge_voice(lang_name)
    return "-".join(voice.split("-")[:2])


# language name -> locale, for the "Speak in" list of the live microphone
SPEECH_LOCALES = {name: get_locale(name) for name in EDGE_VOICE_MAP}

# live-translation folder (temporary speech files)
LIVE_DIR = os.path.join(OUTPUT_DIR, "live")
os.makedirs(LIVE_DIR, exist_ok=True)
