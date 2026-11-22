"""pyttsx3 worker. Runs in its OWN process, so Flask threads / COM apartments can not break it.

Input  (stdin, UTF-8 JSON): {"text", "path", "voice", "speed", "volume"}
Output: writes the audio file.  Exit codes: 0 = OK, 2 = Python error, 3 = no file written.
Errors are printed to stderr (the server shows them on screen).
"""
import json
import os
import sys
import time
import traceback


def main():
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    path = data["path"]

    import pyttsx3  # imported here so a missing package gives a clear message

    last_voice_count = 0
    for attempt in (1, 2):
        engine = pyttsx3.init()
        voices = engine.getProperty("voices") or []
        last_voice_count = len(voices)
        if data.get("voice") is not None and voices:
            idx = 0 if data["voice"] == "Male" else (1 if len(voices) > 1 else 0)
            engine.setProperty("voice", voices[idx].id)
        if data.get("speed") is not None:
            engine.setProperty("rate", int(data["speed"]))
        if data.get("volume") is not None:
            engine.setProperty("volume", float(data["volume"]))
        engine.save_to_file(data["text"], path)
        engine.runAndWait()
        try:
            engine.stop()
        except Exception:
            pass
        time.sleep(0.3)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return 0
    sys.stderr.write(
        "pyttsx3 ran without errors but wrote no audio file "
        "(voices found on this PC: %d, target: %s)\n" % (last_voice_count, path))
    return 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc()
        sys.exit(2)
