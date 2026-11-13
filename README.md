# FB Live Transcriber

A Windows desktop app that transcribes Facebook livestreams and videos to text in near real time. Paste a URL, click **Start**, and the transcript appears as the stream plays. Everything runs locally, so no audio is sent to a cloud service.

## Features

- Live transcription with about 12 seconds of delay
- Works on Facebook live streams and regular videos
- Two engines: **Whisper** (English, Tagalog, Spanish, Japanese, etc.) and **Meta MMS** (Ilocano, Cebuano, Tagalog, English)
- Whisper model sizes from `tiny` to `large-v3`
- Export the transcript as `.txt` (with timestamps) or `.srt` (subtitles)
- Private or group streams are supported through your browser's login cookies

## Download

**From GitHub Actions**
1. Open the repo's **Actions** tab, choose the latest "Build Windows exe" run, and download the `FBLiveTranscriber-win64` artifact.
2. If a tagged release exists, download the zip from the **Releases** page instead.
3. Unzip it and run `FBLiveTranscriber.exe`.

## Usage

1. Paste the Facebook video or live URL.
2. Pick an **Engine**, then a **Model** (Whisper only) and a **Language** (see the tables below). Use the MMS engine for Ilocano or Cebuano.
3. If the stream is private or members-only, set **Cookies from** to the browser you're logged into Facebook with.
4. Click **Start**. Click **Stop** to end the capture.
5. Click **Save...** to export the transcript.

The first run of each engine or model downloads it, which can take a few minutes.

### Choosing an engine

| Engine | Use for | Notes |
|---|---|---|
| Whisper | Most languages, including Tagalog | Punctuation, real timestamps, VAD. Best general choice |
| MMS | Ilocano, Cebuano (not supported by Whisper) | About 3.5 GB download on first use, no punctuation, one timestamp per 12 s chunk, needs a fast CPU or GPU |

Whisper does not support Ilocano or Cebuano at all, which is why MMS is included.

### Choosing a Whisper model

| Model | Download size | Speed on a typical CPU | Accuracy |
|---|---|---|---|
| `tiny` | about 75 MB | Very fast | Basic |
| `base` | about 140 MB | Fast | OK for clear English |
| `small` | about 480 MB | Real time on most PCs | Good (default) |
| `medium` | about 1.5 GB | Needs a decent CPU or GPU | Better for Tagalog and Taglish |
| `large-v3` | about 3 GB | Needs a GPU to keep up | Best |

The model dropdown is disabled when the MMS engine is selected. If the status bar shows the transcript falling behind the stream, switch to a smaller Whisper model.

## Build it yourself

The MMS engine adds PyTorch and `transformers` to the build, so the `.exe` is large (likely over 1 GB).

**With GitHub Actions** (no Windows PC needed): push to `main`, or run the workflow manually from the Actions tab. Push a tag like `v1.0` to also publish a Release.

**On Windows:** install Python 3.10 or newer, then double-click `build.bat`. It downloads `yt-dlp.exe` and `ffmpeg.exe`, installs the dependencies and builds `dist\FBLiveTranscriber\FBLiveTranscriber.exe`.

**Run from source:**
```bash
pip install faster-whisper numpy
pip install torch transformers   # only needed for the MMS engine
# put yt-dlp.exe and ffmpeg.exe in the bin\ folder (or on PATH)
python app.py
```

## How it works

```
Facebook URL -> yt-dlp -> ffmpeg (16 kHz mono audio) -> Whisper or MMS -> text window
```

Audio is cut into 12-second chunks. Whisper uses voice-activity detection to skip silence; MMS skips chunks that are nearly silent. Words that fall across a chunk boundary can occasionally be cut or garbled.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Missing tool" error | `yt-dlp.exe` or `ffmpeg.exe` is not in `bin\` or on PATH |
| Error right after clicking Start | Update `yt-dlp.exe`. Facebook changes its pages often |
| "Login required" or empty result | Set **Cookies from** to the browser you're logged into |
| Transcript lags behind the stream | Use a smaller Whisper model (MMS has no smaller option) |
| MMS is slow or runs out of memory | Close other apps; MMS needs about 4 GB RAM and a fast CPU |
| Poor Tagalog accuracy | Use `medium` or `large-v3` and select the language explicitly |

## Legal

© 2026 eihcek. Free for non-commercial use only under the [PolyForm Noncommercial License 1.0.0](LICENSE). Commercial use requires permission from the author.

Only record and transcribe streams you own or have permission to use. Respect Facebook's terms and the broadcaster's rights.

## Project layout

```
app.py          # the whole application (tkinter GUI + pipeline)
build.bat       # Windows build script (PyInstaller)
requirements.txt
LICENSE         # PolyForm Noncommercial 1.0.0
icon.ico        # app icon
make_icon.py    # regenerates icon.ico (needs pillow)
.github/workflows/build.yml   # CI build that produces the .exe zip
```
