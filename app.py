"""FB Live Transcriber - captures a Facebook livestream and transcribes it live."""
import os, re, sys, shutil, subprocess, threading, queue, time, datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

SAMPLE_RATE = 16000
CHUNK_SECONDS = 12
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)

WHISPER_LANGS = {"Auto-detect": None, "English": "en", "Tagalog/Filipino": "tl",
                 "Spanish": "es", "Japanese": "ja", "Korean": "ko",
                 "Chinese": "zh", "Indonesian": "id"}
# Meta MMS uses ISO 639-3 codes
MMS_LANGS = {"Ilocano": "ilo", "Cebuano": "ceb", "Tagalog": "tgl", "English": "eng"}
ENGINES = ["Whisper", "MMS (Ilocano, Cebuano...)"]
MODELS = ["tiny", "base", "small", "medium", "large-v3"]
# languages pyspellchecker ships dictionaries for (others are not checked)
SPELL_LANGS = {"en", "es", "fr", "pt", "de", "it", "ru", "nl"}
WORD_RE = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)*")


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


def hf_download(repo_id, allow_patterns, report):
    """Download a Hugging Face repo snapshot, calling report(done_bytes, total_bytes) as it goes.
    Falls back to the local cache if offline. Returns the local directory."""
    import io, threading
    from huggingface_hub import snapshot_download
    from huggingface_hub.utils import tqdm as hf_tqdm

    lock = threading.Lock()
    bars = {}  # id(bar) -> [done, total]
    last = [0.0]

    def push(force=False):
        now = time.time()
        if not force and now - last[0] < 0.1:
            return
        last[0] = now
        report(sum(b[0] for b in bars.values()), sum(b[1] for b in bars.values()))

    class Bar(hf_tqdm):
        def __init__(self, *a, **k):
            k["file"] = io.StringIO()  # no console in the windowed exe
            super().__init__(*a, **k)
            self.is_bytes = k.get("unit") == "B"
            if self.is_bytes:
                with lock:
                    bars[id(self)] = [k.get("initial") or 0, k.get("total") or 0]

        def update(self, n=1):
            r = super().update(n)
            if self.is_bytes and n:
                with lock:
                    b = bars[id(self)]
                    b[0] += n
                    if self.total:
                        b[1] = self.total
                    push()
            return r

    try:
        path = snapshot_download(repo_id, allow_patterns=allow_patterns, tqdm_class=Bar)
        report(1, 1)  # finished: lets the UI hide the bar
        return path
    except Exception:
        report(1, 1)
        return snapshot_download(repo_id, allow_patterns=allow_patterns, local_files_only=True)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FB Live Transcriber")
        try:
            base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
            self.iconbitmap(os.path.join(base, "icon.ico"))
        except Exception:
            pass  # non-Windows or icon missing
        self.geometry("820x600")
        self.q = queue.Queue()
        self.stop_evt = threading.Event()
        self.procs = []
        self.worker = None
        self.lines = []  # (start, end, text)
        self.line_langs = {}  # line index -> language code of that line
        self.checkers = {}  # language code -> SpellChecker (or None if unavailable)
        self.ignored = set()

        top = ttk.Frame(self, padding=8); top.pack(fill="x")
        ttk.Label(top, text="Facebook video/live URL:").grid(row=0, column=0, sticky="w")
        self.url = tk.StringVar()
        ttk.Entry(top, textvariable=self.url).grid(row=1, column=0, columnspan=6, sticky="ew", pady=2)
        top.columnconfigure(0, weight=1)

        ttk.Label(top, text="Engine").grid(row=2, column=0, sticky="w")
        self.engine = tk.StringVar(value=ENGINES[0])
        eng = ttk.Combobox(top, textvariable=self.engine, values=ENGINES, width=24, state="readonly")
        eng.grid(row=3, column=0, sticky="w")
        eng.bind("<<ComboboxSelected>>", lambda e: self.on_engine())
        ttk.Label(top, text="Model").grid(row=2, column=1, sticky="w", padx=8)
        self.model = tk.StringVar(value="small")
        self.model_cb = ttk.Combobox(top, textvariable=self.model, values=MODELS, width=10, state="readonly")
        self.model_cb.grid(row=3, column=1, sticky="w", padx=8)
        ttk.Label(top, text="Language").grid(row=2, column=2, sticky="w")
        self.lang = tk.StringVar(value="Auto-detect")
        self.lang_cb = ttk.Combobox(top, textvariable=self.lang, values=list(WHISPER_LANGS), width=18, state="readonly")
        self.lang_cb.grid(row=3, column=2)
        ttk.Label(top, text="Cookies from").grid(row=2, column=3, sticky="w", padx=8)
        self.cookies = tk.StringVar(value="none")
        ttk.Combobox(top, textvariable=self.cookies, values=["none", "chrome", "edge", "firefox"], width=9, state="readonly").grid(row=3, column=3, padx=8)
        self.btn = ttk.Button(top, text="Start", command=self.toggle); self.btn.grid(row=3, column=4, padx=4)
        ttk.Button(top, text="Save...", command=self.save).grid(row=3, column=5)
        self.spellcheck = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Spellcheck", variable=self.spellcheck,
                        command=self.recheck_all).grid(row=3, column=6, padx=(8, 0))

        self.out = scrolledtext.ScrolledText(self, wrap="word", font=("Segoe UI", 11))
        self.out.pack(fill="both", expand=True, padx=8, pady=4)
        self.out.tag_config("misspelled", underline=True, foreground="#c00000")
        self.out.bind("<Button-3>", self.on_right_click)
        self.status = tk.StringVar(value="Idle")
        foot = ttk.Frame(self); foot.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Label(foot, textvariable=self.status, anchor="w").pack(side="left")
        self.pbar = ttk.Progressbar(foot, length=180, mode="determinate", maximum=100)  # shown only while downloading
        ttk.Label(foot, text="\u00a9 2026 eihcek. Non-commercial use only.", foreground="gray").pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(150, self.poll)

    # ---- UI helpers
    def is_mms(self):
        return self.engine.get() == ENGINES[1]

    def on_engine(self):
        if self.is_mms():
            self.lang_cb.config(values=list(MMS_LANGS)); self.lang.set("Ilocano")
            self.model_cb.config(state="disabled")
        else:
            self.lang_cb.config(values=list(WHISPER_LANGS)); self.lang.set("Auto-detect")
            self.model_cb.config(state="readonly")

    def poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "text":
                    i, line, lang = val
                    self.line_langs[i] = lang
                    self.out.insert("end", line, (f"L{i}",)); self.out.insert("end", "\n")
                    self.check_line(i); self.out.see("end")
                elif kind == "status":
                    self.status.set(val)
                elif kind == "progress":
                    done, total = val
                    if total and done < total:
                        if not self.pbar.winfo_ismapped():
                            self.pbar.pack(side="left", padx=8)
                        self.pbar["value"] = 100.0 * done / total
                        self.status.set(f"Downloading model: {done / 1e6:,.0f} / {total / 1e6:,.0f} MB "
                                        f"({100.0 * done / total:.0f}%)")
                    else:
                        self.pbar.pack_forget()
                elif kind == "done":
                    self.pbar.pack_forget()
                    self.btn.config(text="Start")
                elif kind == "error":
                    messagebox.showerror("Error", val)
        except queue.Empty:
            pass
        self.after(150, self.poll)

    # ---- spellcheck
    def spell(self, lang):
        if lang not in SPELL_LANGS:
            return None
        if lang not in self.checkers:
            try:
                from spellchecker import SpellChecker
                self.checkers[lang] = SpellChecker(language=lang)
            except Exception as e:
                self.checkers[lang] = None
                self.status.set(f"Spellcheck unavailable: {e}")
        return self.checkers[lang]

    def check_line(self, i):
        rng = self.out.tag_ranges(f"L{i}")
        if not rng:
            return
        start, end = str(rng[0]), str(rng[1])
        self.out.tag_remove("misspelled", start, end)
        sc = self.spellcheck.get() and self.spell(self.line_langs.get(i))
        if not sc:
            return
        text = self.out.get(start, end)
        body = text.find("] ") + 2 if text.startswith("[") else 0  # skip timestamp
        for m in WORD_RE.finditer(text, body):
            w = m.group().lower()
            if len(w) > 1 and w not in self.ignored and w not in sc:
                self.out.tag_add("misspelled", f"{start}+{m.start()}c", f"{start}+{m.end()}c")

    def recheck_all(self):
        for i in self.line_langs:
            self.check_line(i)
        if self.spellcheck.get() and self.line_langs and \
                not any(self.spell(l) for l in set(self.line_langs.values())):
            self.status.set("Spellcheck: no dictionary for this language (English/Spanish only)")

    def on_right_click(self, e):
        idx = self.out.index(f"@{e.x},{e.y}")
        tags = self.out.tag_names(idx)
        if "misspelled" not in tags:
            return
        line_tags = [t for t in tags if t.startswith("L") and t[1:].isdigit()]
        if not line_tags:
            return
        i = int(line_tags[0][1:])
        a, b = (str(x) for x in self.out.tag_prevrange("misspelled", idx + "+1c"))
        word = self.out.get(a, b)
        sc = self.spell(self.line_langs.get(i))
        if not sc:
            return
        cands = sorted((c for c in (sc.candidates(word.lower()) or ()) if c != word.lower()),
                       key=sc.word_usage_frequency, reverse=True)[:6]
        menu = tk.Menu(self, tearoff=0)
        for c in cands:
            c = c.capitalize() if word[0].isupper() else c
            menu.add_command(label=c, command=lambda c=c: self.replace_word(i, a, b, c))
        if not cands:
            menu.add_command(label="(no suggestions)", state="disabled")
        menu.add_separator()
        menu.add_command(label=f'Ignore "{word}"', command=lambda: self.ignore_word(word))
        menu.tk_popup(e.x_root, e.y_root)

    def replace_word(self, i, a, b, new):
        self.out.delete(a, b)
        self.out.insert(a, new, (f"L{i}",))
        rng = self.out.tag_ranges(f"L{i}")
        text = self.out.get(str(rng[0]), str(rng[1]))
        body = text[text.find("] ") + 2:] if text.startswith("[") else text
        st, en, _ = self.lines[i]
        self.lines[i] = (st, en, body)  # so Save... exports the correction
        self.check_line(i)

    def ignore_word(self, word):
        self.ignored.add(word.lower())
        self.recheck_all()

    def toggle(self):
        if self.worker and self.worker.is_alive():
            self.stop(); return
        if not self.url.get().strip():
            messagebox.showwarning("URL needed", "Paste a Facebook video/live URL."); return
        for t in ("yt-dlp", "ffmpeg"):
            if not find_tool(t):
                messagebox.showerror("Missing tool", f"{t} not found. Put {t}.exe in the app's bin folder."); return
        self.stop_evt.clear(); self.lines.clear(); self.line_langs.clear(); self.out.delete("1.0", "end")
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
            self.q.put(("status", "Checking model files (first run downloads them)..."))
            import numpy as np
            if self.is_mms():
                import torch
                from transformers import Wav2Vec2ForCTC, AutoProcessor
                code = MMS_LANGS[self.lang.get()]
                mms_dir = hf_download("facebook/mms-1b-all",
                                      ["config.json", "preprocessor_config.json", "special_tokens_map.json",
                                       "tokenizer_config.json", "vocab.json", "model.safetensors",
                                       f"adapter.{code}.safetensors"],
                                      lambda d, t: self.q.put(("progress", (d, t))))
                self.q.put(("status", "Loading MMS model into memory (can take a minute)..."))
                proc =AutoProcessor.from_pretrained(mms_dir, target_lang=code)
                mms = Wav2Vec2ForCTC.from_pretrained(mms_dir, target_lang=code,
                                                     ignore_mismatched_sizes=True).eval()

                mms_lang = {"eng": "en"}.get(code)  # spellcheck language

                def transcribe(audio, dur):
                    if float(np.sqrt(np.mean(audio ** 2))) < 0.005:  # near-silence
                        return [], mms_lang
                    inp = proc(audio, sampling_rate=SAMPLE_RATE, return_tensors="pt")
                    with torch.no_grad():
                        ids = torch.argmax(mms(**inp).logits, dim=-1)[0]
                    txt = proc.decode(ids).strip()
                    return ([(0.0, dur, txt)] if txt else []), mms_lang
            else:
                from faster_whisper import WhisperModel
                model_dir = hf_download(f"Systran/faster-whisper-{self.model.get()}",
                                        ["config.json", "preprocessor_config.json", "model.bin",
                                         "tokenizer.json", "vocabulary.*"],
                                        lambda d, t: self.q.put(("progress", (d, t))))
                self.q.put(("status", f"Loading Whisper {self.model.get()} into memory..."))

                def cpu_model():
                    return WhisperModel(model_dir, device="cpu", compute_type="int8")
                try:
                    wm = WhisperModel(model_dir, device="auto", compute_type="auto")
                except Exception:
                    wm = cpu_model()
                lang = WHISPER_LANGS[self.lang.get()]

                def transcribe(audio, dur):
                    nonlocal wm
                    def go():
                        segs, info = wm.transcribe(audio, language=lang, vad_filter=True, beam_size=1)
                        return list(segs), info.language
                    try:
                        segs, detected = go()
                    except RuntimeError as e:  # e.g. libcublas/CUDA libs missing
                        if "cublas" not in str(e).lower() and "cuda" not in str(e).lower() and "cudnn" not in str(e).lower():
                            raise
                        self.q.put(("status", "GPU unavailable, using CPU..."))
                        wm = cpu_model()
                        segs, detected = go()
                    return [(x.start, x.end, x.text.strip()) for x in segs], lang or detected

            ytcmd = [find_tool("yt-dlp"), "-q", "--no-warnings", "-f", "wa*/worst[height>=240]/worst/best",
                     "--ffmpeg-location", os.path.dirname(find_tool("ffmpeg")) or ".",
                     "-o", "-", self.url.get().strip()]
            if self.cookies.get() != "none":
                ytcmd[1:1] = ["--cookies-from-browser", self.cookies.get()]
            ffcmd = [find_tool("ffmpeg"), "-loglevel", "error", "-i", "pipe:0", "-vn",
                     "-f", "s16le", "-ac", "1", "-ar", str(SAMPLE_RATE), "pipe:1"]

            self.q.put(("status", "Model ready. Opening stream..."))
            yt = subprocess.Popen(ytcmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=NOWIN)
            ff = subprocess.Popen(ffcmd, stdin=yt.stdout, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=NOWIN)
            yt.stdout.close()
            self.procs = [yt, ff]
            self.q.put(("status", "Connecting to stream (yt-dlp)..."))

            chunk_bytes = SAMPLE_RATE * 2 * CHUNK_SECONDS
            offset = 0.0
            first = True
            while not self.stop_evt.is_set():
                buf = b""
                while len(buf) < chunk_bytes:
                    d = ff.stdout.read(chunk_bytes - len(buf))
                    if not d: break
                    if first:
                        first = False
                        self.q.put(("status", f"Stream open. Buffering first {CHUNK_SECONDS}s of audio..."))
                    buf += d
                if len(buf) < SAMPLE_RATE * 2:  # <1s => stream ended
                    break
                self.q.put(("status", f"Transcribing audio from {fmt_ts(offset)}..."))
                audio = np.frombuffer(buf, np.int16).astype(np.float32) / 32768.0
                segs, seg_lang = transcribe(audio, len(buf) / 2 / SAMPLE_RATE)
                for st, en, txt in segs:
                    if txt:
                        a, b = offset + st, offset + en
                        self.lines.append((a, b, txt))
                        self.q.put(("text", (len(self.lines) - 1, f"[{fmt_ts(a)}] {txt}", seg_lang)))
                offset += len(buf) / 2 / SAMPLE_RATE
                self.q.put(("status", f"Listening... transcribed {fmt_ts(offset)} of stream"))

            if not self.stop_evt.is_set():
                try: yt.wait(timeout=3)
                except Exception: pass
                err = yt.stderr.read().decode(errors="ignore").strip() if yt.poll() is not None else ""
                if err:
                    self.q.put(("error", f"Stream ended after {fmt_ts(offset)} (yt-dlp exit {yt.returncode}):\n" + err[-600:]))
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
