"""Local speech documents, checkpointed SenseVoice inference and original audio."""
import copy
import json
import re
import shutil
import time
import uuid
from pathlib import Path
from threading import RLock

from .douyin import check_cancel
from .engine import Engine
from .media import run_ffmpeg
from .models import AppError, Cancelled, VideoInfo
from .speech_models import SpeechModels

SAMPLE_RATE = 16000
PCM_LIMIT = 512*1024*1024


def document_text(doc):
    if doc.get("edited_text") is not None:
        return doc["edited_text"]
    result = ""
    for part in doc.get("segments", []):
        text = part.get("text", "").strip()
        if result and text and result[-1].isascii() and text[0].isascii() and text[0].isalnum():
            result += " "
        result += text
    return result


def text_ranges(doc):
    if doc.get("edited_text") is not None:
        return []  # Editing cannot invent alignment with the original waveform.
    result, ranges = "", []
    for part in doc.get("segments", []):
        text = part.get("text", "").strip()
        if result and text and result[-1].isascii() and text[0].isascii() and text[0].isalnum():
            result += " "
        start = len(result)
        result += text
        ranges.append({"from": start, "to": len(result), **part})
    return ranges


def word_timings(text, tokens, stamps, durations, base, end):
    if len(tokens) != len(stamps):
        return []
    words, cursor, previous = [], 0, -1
    for i, raw in enumerate(tokens):
        token = re.sub(r"<\|[^|]*\|>", "", raw).replace("▁", " ").strip()
        if not token:
            continue
        offset = text.find(token, cursor)
        if offset < 0:
            continue
        start = max(base, min(end, base+float(stamps[i])))
        if start < previous:
            continue
        until = end
        if len(durations) == len(tokens) and durations[i] > 0:
            until = min(end, start+float(durations[i]))
        else:
            until = next((min(end, base+float(t)) for t in stamps[i+1:] if base+float(t) > start), end)
        cursor = offset+len(token)
        previous = start
        if until > start:
            words.append({"from": offset, "to": cursor, "start": start, "end": until})
    return words


class TranscriptStore:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.root = self.data_dir/"transcripts"
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()

    def folder(self, key):
        if not re.fullmatch(r"[a-f0-9]{32}", key):
            raise AppError("文案编号无效。")
        return self.root/key

    def create(self, title, source="", platform="本地文件"):
        doc = {"id": uuid.uuid4().hex, "title": title[:200], "source": source, "platform": platform,
               "created": time.time(), "state": "new", "segments": [], "resume": 0, "duration": 0,
               "model": "SenseVoice Small int8 2024-07-17", "edited_text": None}
        self.save(doc)
        return doc

    def read(self, key):
        with self.lock:
            try:
                return json.loads((self.folder(key)/"document.json").read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                raise AppError("文案暂时无法读取，原文件已保留。") from error

    def save(self, doc):
        with self.lock:
            folder = self.folder(doc["id"])
            folder.mkdir(exist_ok=True)
            temporary = folder/"document.tmp"
            temporary.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(folder/"document.json")

    def rows(self, query=""):
        result = []
        for file in self.root.glob("*/document.json"):
            try:
                doc = self.read(file.parent.name)
                if query.casefold() in (doc.get("title", "")+" "+document_text(doc)).casefold():
                    result.append(doc)
            except AppError:
                continue
        return sorted(result, key=lambda x: x.get("created", 0), reverse=True)

    def edit(self, key, text):
        doc = self.read(key)
        doc["edited_text"] = text
        self.save(doc)
        return doc

    def restore_original(self, key):
        doc = self.read(key)
        doc["edited_text"] = None
        self.save(doc)
        return doc

    def delete(self, key):
        # Only the private, validated document folder; original media stays put.
        folder = self.folder(key)
        if folder.is_symlink():
            raise AppError("文案目录异常，已停止删除。")
        shutil.rmtree(folder)


class LocalSpeech:
    def __init__(self, store, cancel, progress=lambda p: None, updated=lambda d: None):
        self.store, self.cancel, self.progress, self.updated = store, cancel, progress, updated
        self.models = SpeechModels(store.data_dir)

    def notify(self, doc):
        self.store.save(doc)
        self.updated(copy.deepcopy(doc))

    def prepare(self, doc, local_path=None, info=None, fmt=None):
        folder = self.store.folder(doc["id"])
        audio = folder/"audio.m4a"
        pcm = folder/"audio.f32"
        if not audio.exists():
            self.progress({"stage": "准备原声", "done": 0, "total": 0})
            info = info or VideoInfo("", "", doc["id"], doc["title"])
            engine = Engine(self.store.data_dir, cancel=self.cancel,
                progress=lambda p: self.progress({**p, "stage": "准备原声"}))
            result = engine.extract_audio(info, fmt, folder, Path(local_path) if local_path else None)
            Path(result.path).replace(audio)
        check_cancel(self.cancel)
        if not pcm.exists():
            self.progress({"stage": "读取音轨", "done": 0, "total": 0})
            temporary = folder/"audio.f32.part"
            try:
                run_ffmpeg(["-i", audio, "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000",
                            "-f", "f32le", "-fs", str(PCM_LIMIT+4), temporary], self.cancel)
                if temporary.stat().st_size > PCM_LIMIT:
                    raise AppError("音频过长，识别缓存超过 512 MB，请先选取较短文件。")
                if temporary.stat().st_size < 640:
                    raise AppError("音轨为空，无法提取文案。")
                temporary.replace(pcm)
            finally:
                temporary.unlink(missing_ok=True)
        doc["audio"] = "audio.m4a"
        doc["duration"] = pcm.stat().st_size/4/SAMPLE_RATE
        self.notify(doc)
        return pcm

    def run(self, doc, local_path=None, info=None, fmt=None, force=False):
        try:
            force = bool(force or doc.get("force", False))
            doc["force"] = force
            self.progress({"stage": "校验离线识别包", "done": 0, "total": 0})
            self.models.validate(self.cancel)
            pcm = self.prepare(doc, local_path, info, fmt)
            import numpy as np
            import sherpa_onnx
            self.progress({"stage": "加载本地模型", "done": 0, "total": 0})
            recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=str(self.models.root/"model.int8.onnx"), tokens=str(self.models.root/"tokens.txt"),
                num_threads=2, use_itn=True, language="auto", provider="cpu", debug=False)
            samples = np.memmap(pcm, dtype="<f4", mode="r")
            total = len(samples)
            if force and doc.get("state") == "unclear":
                doc["resume"] = 0
            base = min(total, int(doc.get("resume", 0)*SAMPLE_RATE))
            doc["state"] = "working"
            doc["error"] = ""
            self.notify(doc)

            def decode(start, stop):
                check_cancel(self.cancel)
                waveform = np.array(samples[start:stop], dtype=np.float32)
                if not len(waveform) or float(np.sqrt(np.mean(waveform**2))) <= .0005:
                    return False
                stream = recognizer.create_stream()
                stream.accept_waveform(SAMPLE_RATE, waveform)
                recognizer.decode_stream(stream)
                check_cancel(self.cancel)
                result = stream.result
                text = re.sub(r"<\|[^|]*\|>", "", result.text).strip()
                if text:
                    part = {"start": start/SAMPLE_RATE, "end": stop/SAMPLE_RATE, "text": text, "original": text,
                            "event": getattr(result, "event", "") or ""}
                    part["words"] = word_timings(text, list(result.tokens), list(result.timestamps),
                        list(getattr(result, "durations", []) or []), part["start"], part["end"])
                    doc["segments"].append(part)
                doc["resume"] = stop/SAMPLE_RATE
                self.notify(doc)
                return "sing" in str(getattr(result, "event", "")).lower()

            if force:
                for start in range(base, total, 20*SAMPLE_RATE):
                    decode(start, min(total, start+20*SAMPLE_RATE))
                    doc["resume"] = min(total, start+20*SAMPLE_RATE)/SAMPLE_RATE
                    self.notify(doc)
                    self.progress({"stage": "本地识别", "done": min(total, start+20*SAMPLE_RATE), "total": total})
            else:
                config = sherpa_onnx.VadModelConfig()
                config.silero_vad.model = str(self.models.root/"silero_vad.onnx")
                config.silero_vad.threshold = .5
                config.silero_vad.min_speech_duration = .25
                config.silero_vad.min_silence_duration = .55
                config.silero_vad.max_speech_duration = 20
                config.sample_rate = SAMPLE_RATE
                config.num_threads = 1
                vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=30)

                def consume():
                    while not vad.empty():
                        part = vad.front
                        start = max(base, int(doc.get("resume", 0)*SAMPLE_RATE), base+part.start-4800)
                        end = min(total, base+part.start+len(part.samples)+1600)
                        song = decode(start, end)
                        vad.pop()
                        if song:
                            doc["state"] = "singing"
                            self.notify(doc)
                            return False
                    return True

                last = 0
                for start in range(base, total, 512):
                    check_cancel(self.cancel)
                    chunk = np.array(samples[start:min(start+512, total)], dtype=np.float32)
                    if len(chunk) < 512:
                        chunk = np.pad(chunk, (0, 512-len(chunk)))
                    vad.accept_waveform(chunk)
                    if not consume():
                        return doc
                    if time.monotonic()-last > .25:
                        self.progress({"stage": "本地识别", "done": start, "total": total})
                        last = time.monotonic()
                vad.flush()
                if not consume():
                    return doc
            check_cancel(self.cancel)
            doc["resume"] = doc["duration"]
            doc["state"] = "done" if doc["segments"] else "unclear"
            self.notify(doc)
            self.progress({"stage": "识别完成", "done": total, "total": total})
            return doc
        except Cancelled:
            doc["state"] = "paused"
            self.notify(doc)
            raise
        except Exception as error:
            doc["state"] = "failed"
            doc["error"] = str(error) if isinstance(error, AppError) else "本地识别未完成，请重试。"
            self.notify(doc)
            raise
