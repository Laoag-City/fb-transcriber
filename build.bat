@echo off
REM Run on Windows. Requires Python 3.10+ on PATH.
if not exist bin mkdir bin
if not exist bin\yt-dlp.exe curl -L -o bin\yt-dlp.exe https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe
if not exist bin\ffmpeg.exe (
  curl -L -o ffmpeg.zip https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
  powershell -Command "Expand-Archive ffmpeg.zip -DestinationPath ffmpeg_tmp -Force"
  for /r ffmpeg_tmp %%f in (ffmpeg.exe) do copy "%%f" bin\ffmpeg.exe
  rmdir /s /q ffmpeg_tmp & del ffmpeg.zip
)
py -3.12 -m venv .venv || exit /b 1
call .venv\Scripts\activate
pip install -r requirements.txt || exit /b 1
pip install torch --index-url https://download.pytorch.org/whl/cpu || exit /b 1
pyinstaller --noconfirm --windowed --icon icon.ico --add-data "icon.ico;." --name FBLiveTranscriber ^
  --collect-all faster_whisper --collect-all ctranslate2 --collect-all transformers --collect-all spellchecker ^
  --add-binary "bin\yt-dlp.exe;." --add-binary "bin\ffmpeg.exe;." app.py || exit /b 1
echo.
echo Done: dist\FBLiveTranscriber\FBLiveTranscriber.exe
