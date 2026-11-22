# Voice Of Mani — PDF to Speech + Live Translation + Image Translation

Same project as `voiceforge_web`, with two new tabs. Your original `main.py` is **not changed**.

| Tab                | What it does                                                                                                      |
| ------------------ | ----------------------------------------------------------------------------------------------------------------- |
| 📄 PDF to Speech   | OCR → clean → translate → speech → ZIP (same as before)                                                           |
| 🌐 Live Translate  | Type or speak. Translation appears live. Can speak the result aloud.                                              |
| 🖼 Image Translate | Upload / paste a picture. Reads the text, translates it, **draws the translation on the picture**, and speaks it. |

| 🌐 https://tesseractocr.org/ | Download tesseract software (important)

## Folder map

```
voiceforge_plus\
├── app.py                  Flask server (all routes)
├── requirements.txt        Python packages (same as before)
├── run.ps1 / run.bat       One-click setup + run
├── backend\
│   ├── config.py           Tesseract path, languages, voices, mic locales
│   ├── ocr.py              PDF OCR + NEW image OCR with text boxes
│   ├── translate.py        Translation (+ NEW line-by-line for the overlay)
│   ├── tts.py              edge-tts, pyttsx3, Windows voice (with exact errors)
│   ├── tts_worker.py       Offline voice, runs in its own process
│   ├── metrics.py          WER, CER, accuracy
│   └── jobs.py             Background pipeline (PDF and image)
├── templates\index.html    Page (3 tabs)
├── static\css\style.css    Light animated theme
├── static\js\theme.js      Automatic colour changing
├── static\js\app.js        Frontend logic
├── tests\smoke_test.py     Automatic check of a running server
└── tests\diagnose_audio.py Shows the EXACT reason when audio fails
```

## Light design and automatic colours

- Clean light design with soft moving shapes, animated buttons, progress bars and cards.
- Colours change **by themselves** every 12 seconds and fade smoothly: Ocean → Lavender → Mint → Sunset.
- Click a colour dot (top right) to keep one colour. Switch **Auto colours** on to let it change again.
- To change the speed, edit `data-interval="12000"` (milliseconds) in `templates\index.html`.
- Computers set to "reduce motion" start with Auto colours off and no animation.

## Run (Windows PowerShell)

```powershell
cd D:\voiceforge_plus
$env:TESSERACT_CMD = "D:\Tesr\tesseract.exe"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\run.ps1
```

Browser opens at http://127.0.0.1:5000

## Test each feature

**Test 1 — automatic check (open a second PowerShell window while the app runs):**

```powershell
cd D:\voiceforge_plus
.\.venv\Scripts\python.exe tests\smoke_test.py tamil
```

You should see `13 / 13 checks passed`.

**Test 2 — Live typing:** click **🌐 Live Translate**, choose **Target Language = Tamil**, type `How are you today?`.
The translation appears about half a second after you stop typing.

**Test 3 — Live microphone:** use **Chrome or Edge**. Click **🎤 Start mic**, allow the microphone, say a sentence.
Tick **Auto-speak translation** to hear each translated sentence. The mic sleeps while the voice speaks.

**Test 4 — Image:** click **🖼 Image Translate**, drop a picture with English text (or press **Ctrl+V** to paste a screenshot),
choose **Target Language**, click **Translate Image**. The **🖼 Image** tab shows the translation on the picture.
Hover a box to see the original text.

## Audio not working? Find the exact error

The page now shows the exact error of every voice step (red or yellow box), and the PowerShell
window prints lines that start with `[TTS]`.

Run the diagnosis (no server needed). It tests the internet, edge-tts, pyttsx3 and the Windows voice one by one:

```powershell
cd D:\voiceforge_plus
.\.venv\Scripts\python.exe tests\diagnose_audio.py
```

Copy everything between `===== START` and `===== END` if you need help.

| Error text                                                   | Meaning                                                             | Fix                                                                                         |
| ------------------------------------------------------------ | ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `WSServerHandshakeError: 403 ... Invalid response status`    | Edge voice server refused the request (old edge-tts or wrong clock) | `.\.venv\Scripts\python.exe -m pip install -U edge-tts` and `w32tm /resync` (Administrator) |
| `ClientConnectorError`, `getaddrinfo failed`, `TimeoutError` | No access to speech.platform.bing.com                               | Check internet, VPN, firewall, proxy                                                        |
| `NoAudioReceived`                                            | Connected, but no audio came back                                   | Try another voice or shorter text                                                           |
| `pyttsx3 worker exit code 3 ... wrote no audio file`         | Windows has no usable offline voice                                 | Run the diagnosis; use Browser voice                                                        |
| `No module named ...`                                        | Package missing                                                     | `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`                             |

Quick workaround in the Live tab: set **Voice output = Browser voice**. It uses the voices built into Edge / Chrome and does not need Python audio.
For PDF and Image jobs, if audio fails you still get the text, the translation and the ZIP.

## Reading non-English text inside images (optional)

Tesseract only reads the languages you installed. List them:

```powershell
& "D:\Tesr\tesseract.exe" --list-langs
```

To add Tamil text reading:

```powershell
Invoke-WebRequest -Uri "https://github.com/tesseract-ocr/tessdata_fast/raw/main/tam.traineddata" -OutFile "D:\Tesr\tessdata\tam.traineddata"
```

Restart the app. **Text language in the image** will now list `tam`.

## Notes

- Translation and Edge voices need internet. pyttsx3 works offline (English only, saves `.wav`).
- The mic uses the browser's speech recognition (Chrome / Edge) and also needs internet. Typing works in every browser.
- Live typing ignores old answers if you keep typing, so the screen never shows stale text.
- Output files are kept in `outputs\` and deleted after 2 hours. To change the port: `$env:PORT = "8000"`.
