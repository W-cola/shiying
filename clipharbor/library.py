"""A content library with transcripts attached to their original media."""
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit

from .speech import document_text

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".avi"}
AUDIO_EXTENSIONS = {".m4a", ".mp3", ".wav", ".flac", ".aac", ".ogg", ".opus", ".wma"}


def identity(value):
    if not value:
        return ""
    if urlsplit(value).scheme in ("http", "https"):
        return value.strip()
    return str(Path(value).resolve()).casefold()


def content_kind(doc):
    if doc.get("media_kind"):
        return doc["media_kind"]
    origin = doc.get("origin") or doc.get("local_path", "")
    return "video" if Path(origin).suffix.lower() in VIDEO_EXTENSIONS or urlsplit(origin or doc.get("source", "")).scheme in ("http", "https") else "audio"


def library_entries(records, documents, kind="", query="", has_text=False):
    entries, by_path, by_url, by_document = [], {}, {}, {}
    for record in records:
        local, source = identity(record["path"]), identity(record.get("url", ""))
        entry = by_path.get(local) or (by_url.get(source) if source else None)
        try:
            created = datetime.fromisoformat(record.get("time", "")).timestamp()
        except ValueError:
            created = 0
        if entry is None:
            entry = {**record, "kind": record.get("kind", "video"), "_record": record, "_records": [], "_doc_ids": [], "_kinds": [], "_search": "", "_created": created}
            if source:
                entry["id"] = "content:"+sha256(source.encode()).hexdigest()[:24]
            entries.append(entry)
        priority = {"video": 3, "images": 2, "audio": 1}
        if priority.get(record.get("kind", "video"), 0) > priority.get(entry.get("kind", "video"), 0):
            for name in ("title", "path", "kind", "files", "size", "platform", "author", "url", "description"):
                if name in record:
                    entry[name] = record[name]
            entry["_record"] = record
            entry["kind"] = record.get("kind", "video")
        entry["_records"].append(record)
        if record.get("kind", "video") not in entry["_kinds"]:
            entry["_kinds"].append(record.get("kind", "video"))
        entry["_created"] = max(entry["_created"], created)
        entry["_search"] += " "+record.get("title", "")+" "+record.get("author", "")
        by_path[local] = entry
        if record.get("origin_path"):
            by_path[identity(record["origin_path"])] = entry
        if source:
            by_url[source] = entry
    pending = list(documents)
    # Older new drafts may reference another document's private audio cache.
    for _ in range(len(pending)+1):
        next_pass = []
        for doc in pending:
            local = identity(doc.get("origin") or doc.get("local_path", ""))
            source = identity(doc.get("source", ""))
            parent = Path(doc.get("local_path", "")).parent.name
            entry = by_path.get(local) or by_url.get(local) or by_url.get(source) or by_document.get(parent)
            if entry is None and len(parent) == 32 and parent in {d["id"] for d in pending} and parent != doc["id"] and parent not in by_document:
                next_pass.append(doc)
                continue
            if entry is None:
                path = doc.get("local_path", "")
                media_kind = content_kind(doc)
                entry = {"id": "transcript:"+doc["id"], "title": doc["title"], "platform": doc.get("platform", "本地文件"),
                         "kind": media_kind, "path": path, "size": 0, "_record": None, "_records": [], "_kinds": [media_kind],
                         "_doc_ids": [], "_search": "", "_created": doc.get("created", 0),
                         "time": datetime.fromtimestamp(doc.get("created", 0)).astimezone().isoformat()}
                entries.append(entry)
                if local:
                    by_path[local] = entry
                if source:
                    by_url[source] = entry
            entry["_doc_ids"].append(doc["id"])
            entry["_search"] += " "+doc["title"]+" "+document_text(doc)
            by_document[doc["id"]] = entry
        if not next_pass:
            break
        if len(next_pass) == len(pending):
            # Malformed/cyclic origins still leave every document discoverable.
            for doc in next_pass:
                doc = {**doc, "local_path": "", "origin": ""}
                entry = {"id": "transcript:"+doc["id"], "title": doc["title"], "kind": doc.get("media_kind", "audio"),
                         "path": "", "size": 0, "platform": doc.get("platform", "本地文件"), "time": "",
                         "_record": None, "_records": [], "_kinds": [doc.get("media_kind", "audio")], "_doc_ids": [doc["id"]], "_search": doc["title"]+" "+document_text(doc), "_created": doc.get("created", 0)}
                entries.append(entry)
            break
        pending = next_pass
    query = query.casefold().strip()
    rank = {d["id"]: index for index, d in enumerate(documents)}
    for entry in entries:
        entry["_doc_ids"].sort(key=lambda key: rank[key])
    return sorted((e for e in entries if (not kind or kind in e["_kinds"])
                  and (not has_text or e["_doc_ids"]) and (not query or query in e["_search"].casefold())),
                  key=lambda e: e["_created"], reverse=True)


def available_forms(entry, documents, transcript_root):
    """Only local, readable assets; a transcript cache is an audio alternative."""
    result = {"video": [], "images": [], "audio": [], "text": []}
    records = entry.get("_records") or ([entry["_record"]] if entry.get("_record") else [])
    candidates = list(records)
    if not records:
        # New drafts may point at another draft's audio cache. Recover the real
        # local original, and never present that .m4a cache as a video.
        for key in entry.get("_doc_ids", []):
            doc = documents.get(key, {})
            for path in (doc.get("origin", ""), doc.get("local_path", "")):
                if not path or urlsplit(path).scheme in ("http", "https"):
                    continue
                suffix = Path(path).suffix.lower()
                kind = "video" if suffix in VIDEO_EXTENSIONS else "audio" if suffix in AUDIO_EXTENSIONS else ""
                if kind:
                    candidates.append({"kind": kind, "path": path})
    seen = set()
    for record in candidates:
        kind = record.get("kind", "video")
        path = record.get("path", "")
        files = record.get("files") or ([path] if path else [])
        if kind not in result or not files or not all(Path(p).is_file() for p in files):
            continue
        key = (kind, identity(path))
        if key not in seen:
            seen.add(key)
            result[kind].append({"path": path, "files": files, "kind": kind, "label": Path(path).name,
                                 "record": record if record in records else None, "time": record.get("time", "")})
    for key in entry.get("_doc_ids", []):
        doc = documents.get(key)
        if not doc:
            continue
        result["text"].append({"kind": "text", "document_id": key, "label": doc["title"], "created": doc.get("created", 0)})
        # Prefer deliberately saved audio; otherwise expose one current replay copy.
        if not result["audio"] and len(key) == 32 and all(c in "0123456789abcdef" for c in key):
            audio = Path(transcript_root)/key/"audio.m4a"
            if audio.is_file():
                result["audio"].append({"path": str(audio), "files": [str(audio)], "kind": "audio",
                                        "label": "原声回听", "record": None, "cached": True})
    return result
