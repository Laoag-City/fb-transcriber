# FB Live Transcriber

A Windows desktop app that transcribes Facebook livestreams and videos to text in near real time. Paste a URL, click **Start**, and the transcript appears as the stream plays. Everything runs locally, so no audio is sent to a cloud service.

## Features

- Live transcription with about 12 seconds of delay
- Works on Facebook live streams and regular videos
- Model sizes from `tiny` to `large-v3`, with Tagalog, Cebuano, English and other languages
- Export the transcript as `.txt` (with timestamps) or `.srt` (subtitles)
- Private or group streams are supported through your browser's login cookies

## Download

**From GitHub Actions**
1. Open the repo's **Actions** tab, choose the latest "Build Windows exe" run, and download the `FBLiveTranscriber-win64` artifact.
2. If a tagged release exists, download the zip from the **Releases** page instead.
3. Unzip it and run `FBLiveTranscriber.exe`.

## Usage

1. Paste the Facebook video or live URL.
2. Pick a **Model** and **Language** (see the table below).
3. If the stream is private or members-only, set **Cookies from** to the browser you're logged into Facebook with.
4. Click **Start**. Click **Stop** to end the capture.
5. Click **Save...** to export the transcript.

The first run downloads the selected Whisper model, which can take a few minutes.

### Choosing a model

| Model | Download size | Speed on a typical CPU | Accuracy |
|---|---|---|---|
| `tiny` | about 75 MB | Very fast | Basic |
| `base` | about 140 MB | Fast | OK for clear English |
| `small` | about 480 MB | Real time on most PCs | Good (default) |
| `medium` | about 1.5 GB | Needs a decent CPU or GPU | Better for Tagalog and Taglish |
| `large-v3` | about 3 GB | Needs a GPU to keep up | Best |

If the status bar shows the transcript falling behind the stream, switch to a smaller model.

## Build it yourself

**With GitHub Actions** (no Windows PC needed): push to `main`, or run the workflow manually from the Actions tab. Push a tag like `v1.0` to also publish a Release.

**On Windows:** install Python 3.10 or newer, then double-click `build.bat`. It downloads `yt-dlp.exe` and `ffmpeg.exe`, installs the dependencies and builds `dist\FBLiveTranscriber\FBLiveTranscriber.exe`.

**Run from source:**
```bash
pip install faster-whisper numpy
# put yt-dlp.exe and ffmpeg.exe in the bin\ folder (or on PATH)
python app.py
```

## How it works

```
Facebook URL -> yt-dlp -> ffmpeg (16 kHz mono audio) -> faster-whisper -> text window
```

Audio is cut into 12-second chunks, and each chunk is transcribed with voice-activity detection to skip silence. Words that fall across a chunk boundary can occasionally be cut or garbled.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Missing tool" error | `yt-dlp.exe` or `ffmpeg.exe` is not in `bin\` or on PATH |
| Error right after clicking Start | Update `yt-dlp.exe`. Facebook changes its pages often |
| "Login required" or empty result | Set **Cookies from** to the browser you're logged into |
| Transcript lags behind the stream | Use a smaller model |
| Poor Tagalog accuracy | Use `medium` or `large-v3` and select the language explicitly |

## Legal

Only record and transcribe streams you own or have permission to use. Respect Facebook's terms and the broadcaster's rights.

## Project layout

```
app.py          # the whole application (tkinter GUI + pipeline)
build.bat       # Windows build script (PyInstaller)
requirements.txt
.github/workflows/build.yml   # CI build that produces the .exe zip
```
