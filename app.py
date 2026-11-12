"""FB Live Transcriber - captures a Facebook livestream and transcribes it live."""
import os, sys, shutil, subprocess, threading, queue, time, datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

SAMPLE_RATE = 16000
CHUNK_SECONDS = 12
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)

LANGS = {"Auto-detect": None, "English": "en", "Tagalog/Filipino": "tl",
         "Cebuano": "ceb", "Spanish": "es", "Japanese": "ja", "Korean": "ko",
         "Chinese": "zh", "Indonesian": "id"}
MODELS = ["tiny", "base", "small", "medium", "large-v3"]


def find_tool(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    for d in (base, os.path.join(base, "bin"), os.path.dirname(sys.executable)):
        for ext in (".exe", ""):
            p = os.path.join(d, name + ext)
            if os.path.isfile(p):
                return p
    return shutil.which(name)


def fmt_ts(s):
    return str(datetime.timedelta(seconds=int(s)))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FB Live Transcriber")
        self.geometry("820x600")
        self.q = queue.Queue()
        self.stop_evt = threading.Event()
        self.procs = []
        self.worker = None
        self.lines = []  # (start, end, text)

        top = ttk.Frame(self, padding=8); top.pack(fill="x")
        ttk.Label(top, text="Facebook video/live URL:").grid(row=0, column=0, sticky="w")
        self.url = tk.StringVar()
        ttk.Entry(top, textvariable=self.url).grid(row=1, column=0, columnspan=6, sticky="ew", pady=2)
        top.columnconfigure(0, weight=1)

        ttk.Label(top, text="Model").grid(row=2, column=0, sticky="w")
        self.model = tk.StringVar(value="small")
        ttk.Combobox(top, textvariable=self.model, values=MODELS, width=10, state="readonly").grid(row=3, column=0, sticky="w")
        ttk.Label(top, text="Language").grid(row=2, column=1, sticky="w", padx=8)
        self.lang = tk.StringVar(value="Auto-detect")
        ttk.Combobox(top, textvariable=self.lang, values=list(LANGS), width=18, state="readonly").grid(row=3, column=1, padx=8)
        ttk.Label(top, text="Cookies from").grid(row=2, column=2, sticky="w")
        self.cookies = tk.StringVar(value="none")
        ttk.Combobox(top, textvariable=self.cookies, values=["none", "chrome", "edge", "firefox"], width=9, state="readonly").grid(row=3, column=2)
        self.btn = ttk.Button(top, text="Start", command=self.toggle); self.btn.grid(row=3, column=3, padx=8)
        ttk.Button(top, text="Save...", command=self.save).grid(row=3, column=4)

        self.out = scrolledtext.ScrolledText(self, wrap="word", font=("Segoe UI", 11))
        self.out.pack(fill="both", expand=True, padx=8, pady=4)
        self.status = tk.StringVar(value="Idle")
        ttk.Label(self, textvariable=self.status, anchor="w").pack(fill="x", padx=8, pady=(0, 6))
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(150, self.poll)

    # ---- UI helpers
    def poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "text":
                    self.out.insert("end", val + "\n"); self.out.see("end")
                elif kind == "status":
                    self.status.set(val)
                elif kind == "done":
                    self.btn.config(text="Start")
                elif kind == "error":
                    messagebox.showerror("Error", val)
        except queue.Empty:
            pass
        self.after(150, self.poll)

    def toggle(self):
        if self.worker and self.worker.is_alive():
            self.stop(); return
        if not self.url.get().strip():
            messagebox.showwarning("URL needed", "Paste a Facebook video/live URL."); return
        for t in ("yt-dlp", "ffmpeg"):
            if not find_tool(t):
                messagebox.showerror("Missing tool", f"{t} not found. Put {t}.exe in the app's bin folder."); return
        self.stop_evt.clear(); self.lines.clear(); self.out.delete("1.0", "end")
        self.btn.config(text="Stop")
        self.worker = threading.Thread(target=self.run, daemon=True); self.worker.start()

    def stop(self):
        self.stop_evt.set()
        for p in self.procs:
            try: p.kill()
            except Exception: pass

    def on_close(self):
        self.stop(); self.destroy()

    def save(self):
        if not self.lines:
            messagebox.showinfo("Nothing to save", "No transcript yet."); return
        path = filedialog.asksaveasfilename(defaultextension=".txt",
                filetypes=[("Text", "*.txt"), ("SubRip subtitles", "*.srt")])
        if not path: return
        with open(path, "w", encoding="utf-8") as f:
            if path.lower().endswith(".srt"):
                def t(s):
                    d = datetime.timedelta(seconds=s); ms = int(d.microseconds / 1000)
                    return f"{str(datetime.timedelta(seconds=int(s))).rjust(8, '0')},{ms:03d}"
                for i, (a, b, x) in enumerate(self.lines, 1):
                    f.write(f"{i}\n{t(a)} --> {t(b)}\n{x}\n\n")
            else:
                for a, b, x in self.lines:
                    f.write(f"[{fmt_ts(a)}] {x}\n")

    # ---- worker
    def run(self):
        try:
            self.q.put(("status", "Loading model (first run downloads it)..."))
            from faster_whisper import WhisperModel
            model = WhisperModel(self.model.get(), device="auto", compute_type="auto")
            lang = LANGS[self.lang.get()]

            ytcmd = [find_tool("yt-dlp"), "-q", "--no-warnings", "-f", "worst[height>=240]/worst/best",
                     "--ffmpeg-location", os.path.dirname(find_tool("ffmpeg")) or ".",
                     "-o", "-", self.url.get().strip()]
            if self.cookies.get() != "none":
                ytcmd[1:1] = ["--cookies-from-browser", self.cookies.get()]
            ffcmd = [find_tool("ffmpeg"), "-loglevel", "error", "-i", "pipe:0", "-vn",
                     "-f", "s16le", "-ac", "1", "-ar", str(SAMPLE_RATE), "pipe:1"]

            yt = subprocess.Popen(ytcmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=NOWIN)
            ff = subprocess.Popen(ffcmd, stdin=yt.stdout, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=NOWIN)
            yt.stdout.close()
            self.procs = [yt, ff]
            self.q.put(("status", "Listening..."))

            import numpy as np
            chunk_bytes = SAMPLE_RATE * 2 * CHUNK_SECONDS
            offset = 0.0
            while not self.stop_evt.is_set():
                buf = b""
                while len(buf) < chunk_bytes:
                    d = ff.stdout.read(chunk_bytes - len(buf))
                    if not d: break
                    buf += d
                if len(buf) < SAMPLE_RATE * 2:  # <1s => stream ended
                    break
                audio = np.frombuffer(buf, np.int16).astype(np.float32) / 32768.0
                segs, _ = model.transcribe(audio, language=lang, vad_filter=True, beam_size=1)
                for s in segs:
                    txt = s.text.strip()
                    if txt:
                        a, b = offset + s.start, offset + s.end
                        self.lines.append((a, b, txt))
                        self.q.put(("text", f"[{fmt_ts(a)}] {txt}"))
                offset += len(buf) / 2 / SAMPLE_RATE
                self.q.put(("status", f"Transcribed {fmt_ts(offset)} of stream"))

            if not self.stop_evt.is_set():
                err = yt.stderr.read().decode(errors="ignore").strip() if yt.poll() is not None else ""
                if offset == 0 and err:
                    self.q.put(("error", err[-600:]))
            self.q.put(("status", "Stopped / stream ended"))
        except Exception as e:
            self.q.put(("error", str(e)))
        finally:
            for p in self.procs:
                try: p.kill()
                except Exception: pass
            self.q.put(("done", None))


if __name__ == "__main__":
    App().mainloop()
