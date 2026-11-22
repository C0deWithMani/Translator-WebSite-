"""Find out EXACTLY why audio does not work. The server does NOT need to be running.

    .\\.venv\\Scripts\\python.exe tests\\diagnose_audio.py
    .\\.venv\\Scripts\\python.exe tests\\diagnose_audio.py --play     (also plays the offline test sound)

It tests, one by one: internet to the Edge voice server, edge-tts (English + Tamil),
pyttsx3 (direct and through the app's worker) and the Windows PowerShell voice.
Copy everything between the START and END lines and send it if something still fails.
"""
import importlib.metadata as md
import os
import platform
import socket
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
PLAY = "--play" in sys.argv
results = []          # (name, ok, detail)
errors_seen = []


def out(text=""):
    print(text, flush=True)


def version(pkg):
    try:
        return md.version(pkg)
    except Exception:
        return "NOT INSTALLED"


def record(name, ok, detail=""):
    results.append((name, ok, detail))
    out(("  PASS  " if ok else "  FAIL  ") + name + (("  ->  " + detail) if detail else ""))


def short_trace():
    lines = traceback.format_exc().strip().splitlines()
    return "\n".join("        " + l for l in lines[-8:])


def run_test(name, func, *args):
    start = time.time()
    try:
        func(*args)
        record(name, True, f"{time.time() - start:.1f}s")
    except Exception as e:
        try:
            from backend.tts import describe
            text = describe(e)
        except Exception:
            text = f"{type(e).__name__}: {e}"
        errors_seen.append(f"{name}: {text}")
        record(name, False, text)
        out(short_trace())


def check_file(path):
    if not os.path.exists(path):
        raise RuntimeError("no file was written")
    size = os.path.getsize(path)
    if size == 0:
        raise RuntimeError("the file is empty (0 bytes)")
    return size


def main():
    out("===== START (copy from here) =====")
    out("")
    out("1) YOUR PC")
    out(f"  Python        : {sys.version.split()[0]}  ({sys.executable})")
    out(f"  Windows       : {platform.platform()}")
    out(f"  Clock (UTC)   : {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}   (must match real UTC time)")
    for pkg in ("edge-tts", "aiohttp", "pyttsx3", "comtypes", "pywin32", "Flask"):
        out(f"  {pkg:<13} : {version(pkg)}")
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY"):
        if os.environ.get(var):
            out(f"  proxy {var} = {os.environ[var]}")

    out("")
    out("2) INTERNET to the Edge voice server")
    try:
        ip = socket.getaddrinfo("speech.platform.bing.com", 443)[0][4][0]
        record("DNS speech.platform.bing.com", True, ip)
    except Exception as e:
        errors_seen.append(f"DNS: {type(e).__name__}: {e}")
        record("DNS speech.platform.bing.com", False, f"{type(e).__name__}: {e}")

    out("")
    out("3) ONLINE voice (edge-tts)")
    tmp = tempfile.mkdtemp(prefix="vf_diag_")
    try:
        from backend import tts
    except Exception as e:
        out(f"  FAIL  cannot import backend.tts -> {type(e).__name__}: {e}")
        out(short_trace())
        out("===== END =====")
        return 1

    def edge_test(voice):
        path = os.path.join(tmp, "edge_" + voice + ".mp3")
        tts.run_edge_tts("Hello, this is a voice test.", voice, path)
        return check_file(path)

    run_test("edge-tts English  (en-US-ChristopherNeural)", edge_test, "en-US-ChristopherNeural")
    run_test("edge-tts Tamil    (ta-IN-ValluvarNeural)", edge_test, "ta-IN-ValluvarNeural")

    out("")
    out("4) OFFLINE voice (pyttsx3)")

    def pyttsx3_direct():
        import pyttsx3
        engine = pyttsx3.init()
        voices = engine.getProperty("voices") or []
        out(f"        voices installed on this PC: {len(voices)}")
        for v in voices[:6]:
            out(f"          - {getattr(v, 'name', v)}")
        path = os.path.join(tmp, "pyttsx3_direct.wav")
        engine.save_to_file("Hello, this is an offline voice test.", path)
        engine.runAndWait()
        check_file(path)

    def pyttsx3_worker():
        path = os.path.join(tmp, "pyttsx3_worker.wav")
        tts.run_pyttsx3("Hello, this is an offline voice test.", path, "Male", 150, 1.0)
        check_file(path)

    def windows_speech():
        path = os.path.join(tmp, "windows_speech.wav")
        tts.run_windows_speech("Hello, this is an offline voice test.", path)
        check_file(path)

    run_test("pyttsx3 directly (this window)", pyttsx3_direct)
    run_test("pyttsx3 through the app worker", pyttsx3_worker)

    out("")
    out("5) OFFLINE voice (Windows PowerShell System.Speech)")
    run_test("Windows System.Speech", windows_speech)

    out("")
    out("6) RESULT")
    ok_names = [n for n, ok, _ in results if ok]
    bad = [(n, d) for n, ok, d in results if not ok]
    out(f"  {len(ok_names)} passed, {len(bad)} failed")
    for n, d in bad:
        out(f"  FAILED: {n}\n          {d}")
    hint = tts.hint_for(errors_seen)
    if hint:
        out("")
        out("  WHAT TO DO: " + hint)
    if not bad:
        out("  Everything works. If the app still has no sound, choose 'Browser voice' in the Live tab "
            "and press Ctrl+F5 in the browser.")
    out("")
    out(f"  Test files are in: {tmp}")
    out("===== END =====")

    if PLAY and os.name == "nt":
        try:
            import winsound
            for name in ("pyttsx3_worker.wav", "pyttsx3_direct.wav", "windows_speech.wav"):
                p = os.path.join(tmp, name)
                if os.path.exists(p) and os.path.getsize(p) > 0:
                    out(f"Playing {name} ...")
                    winsound.PlaySound(p, winsound.SND_FILENAME)
                    break
        except Exception as e:
            out(f"Could not play: {type(e).__name__}: {e}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
