"""Text to speech with a fallback chain. EVERY failure keeps its exact error text.

Order for the "edge" engine:
    1. edge-tts, voice of the chosen language      (online, neural)
    2. edge-tts, default English voice              (online, neural)
    3. pyttsx3 in a separate process                (offline)
    4. Windows System.Speech via PowerShell         (offline, Windows only)
For the "pyttsx3" engine only steps 3 and 4 are used.
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile

import edge_tts

from .config import DEFAULT_VOICE

WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tts_worker.py")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)   # Windows: no flashing console


class TTSError(Exception):
    """Raised when every voice failed. .errors = one exact message per attempt."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("\n".join(self.errors))


def describe(exc):
    """'ClassName: message' (+ HTTP status when the error has one, e.g. 403)."""
    text = f"{type(exc).__name__}: {exc}"
    status = getattr(exc, "status", None)
    if status is not None and str(status) not in text:
        text += f" (HTTP status {status})"
    return text


def hint_for(errors):
    """Plain-English next step for the most common errors."""
    blob = " ".join(errors).lower()
    hints = []
    if "403" in blob or "invalid response status" in blob:
        hints.append("edge-tts got HTTP 403. Fix: update it with "
                     "'pip install -U edge-tts' and sync the Windows clock (run 'w32tm /resync' as Administrator).")
    if any(k in blob for k in ("getaddrinfo", "cannot connect", "connectorerror", "timeouterror",
                               "timed out", "connection reset", "name or service not known")):
        hints.append("edge-tts could not reach speech.platform.bing.com. Check internet, firewall, VPN or proxy.")
    if "ssl" in blob or "certificate" in blob:
        hints.append("An SSL / certificate error: a proxy or antivirus may be inspecting the connection.")
    if "noaudioreceived" in blob:
        hints.append("edge-tts connected but received no audio. Try another voice or shorter text.")
    if "no module named" in blob:
        hints.append("A Python package is missing. Run: .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt")
    if "wrote no audio file" in blob or "exit code" in blob:
        hints.append("The offline voice failed. Run tests\\diagnose_audio.py to see the exact reason, "
                     "or choose 'Browser voice' in the Live tab.")
    return " ".join(hints)


# ---------------- edge-tts ----------------
async def _edge_generate(text, voice, output_path):
    await edge_tts.Communicate(text, voice).save(output_path)


def run_edge_tts(text, voice, audio_path):
    asyncio.run(asyncio.wait_for(_edge_generate(text, voice, audio_path), timeout=90))
    if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
        raise RuntimeError("edge-tts finished but wrote an empty file")


# ---------------- pyttsx3 (separate process) ----------------
def run_pyttsx3(text, audio_path, voice_choice=None, speed=None, volume=None):
    payload = {"text": text, "path": audio_path, "voice": voice_choice,
               "speed": speed, "volume": volume}
    try:
        proc = subprocess.run(
            [sys.executable, WORKER], input=json.dumps(payload),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=180, creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired:
        raise RuntimeError("pyttsx3 worker timed out after 180 seconds")
    ok = os.path.exists(audio_path) and os.path.getsize(audio_path) > 0
    if proc.returncode != 0 or not ok:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"pyttsx3 worker exit code {proc.returncode}: "
                           f"{detail[-700:] if detail else 'no output'}")


# ---------------- Windows System.Speech (last resort) ----------------
_PS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$text = [System.IO.File]::ReadAllText($env:VF_TEXT, [System.Text.Encoding]::UTF8)
$s.Rate = [int]$env:VF_RATE
$s.Volume = [int]$env:VF_VOLUME
if ($env:VF_GENDER) {
  try { $s.SelectVoiceByHints([System.Enum]::Parse([System.Speech.Synthesis.VoiceGender], $env:VF_GENDER)) } catch {}
}
$s.SetOutputToWaveFile($env:VF_OUT)
$s.Speak($text)
$s.Dispose()
"""


def run_windows_speech(text, audio_path, voice_choice=None, speed=None, volume=None):
    if os.name != "nt":
        raise RuntimeError("Windows System.Speech is only available on Windows")
    ps = shutil.which("powershell") or shutil.which("pwsh")
    if not ps:
        raise RuntimeError("powershell.exe was not found")
    rate = 0 if speed is None else max(-10, min(10, round((int(speed) - 150) / 12)))
    vol = 100 if volume is None else max(0, min(100, int(float(volume) * 100)))
    with tempfile.TemporaryDirectory() as tmp:
        txt_path = os.path.join(tmp, "text.txt")
        ps_path = os.path.join(tmp, "speak.ps1")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text)
        with open(ps_path, "w", encoding="utf-8") as f:
            f.write(_PS_SCRIPT)
        env = dict(os.environ, VF_TEXT=txt_path, VF_OUT=audio_path, VF_RATE=str(rate), VF_VOLUME=str(vol),
                   VF_GENDER=(voice_choice or "") if voice_choice in ("Male", "Female") else "")
        try:
            proc = subprocess.run(
                [ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", ps_path],
                env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=180, creationflags=NO_WINDOW)
        except subprocess.TimeoutExpired:
            raise RuntimeError("PowerShell speech timed out after 180 seconds")
    ok = os.path.exists(audio_path) and os.path.getsize(audio_path) > 0
    if proc.returncode != 0 or not ok:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"PowerShell exit code {proc.returncode}: {detail[-700:] if detail else 'no output'}")


# ---------------- the chain ----------------
def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def synthesize(text, out_base, engine_choice, edge_voice, voice_choice, speed, volume, note):
    """
    Returns (audio_path, mime_type, voice_label).
    note(msg) receives every warning with its exact error text.
    Raises TTSError (with all error messages) when nothing worked.
    """
    errors = []

    def failed(label, exc):
        msg = f"{label}: {describe(exc)}"
        errors.append(msg)
        note(msg)
        print("[TTS] " + msg, flush=True)       # also visible in the PowerShell window

    custom = engine_choice == "pyttsx3"

    if not custom:
        mp3_path = out_base + ".mp3"
        voices = [edge_voice] if edge_voice == DEFAULT_VOICE else [edge_voice, DEFAULT_VOICE]
        for voice in voices:
            try:
                run_edge_tts(text, voice, mp3_path)
                return mp3_path, "audio/mpeg", voice
            except Exception as e:
                failed(f"edge-tts ({voice})", e)
                _remove(mp3_path)
        note("Online voice failed - trying the offline voices...")

    wav_path = out_base + ".wav"
    args = (voice_choice, speed, volume) if custom else (None, None, None)
    try:
        run_pyttsx3(text, wav_path, *args)
        if custom:
            note("pyttsx3 speaks English only. Use edge-tts for translated audio.")
        return wav_path, "audio/wav", "pyttsx3 offline"
    except Exception as e:
        failed("pyttsx3", e)
        _remove(wav_path)
    try:
        run_windows_speech(text, wav_path, *args)
        if custom:
            note("Windows offline voice speaks English only. Use edge-tts for translated audio.")
        return wav_path, "audio/wav", "Windows offline voice"
    except Exception as e:
        failed("Windows System.Speech", e)
        _remove(wav_path)

    raise TTSError(errors)
