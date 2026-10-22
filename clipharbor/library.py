"""A content library with transcripts attached to their original media."""
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from .speech import document_text

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".avi"}


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
        entry = {**record, "_record": record, "_doc_ids": [], "_search": record.get("title", "")+" "+record.get("author", "")}
        try:
            entry["_created"] = datetime.fromisoformat(record.get("time", "")).timestamp()
        except ValueError:
            entry["_created"] = 0
        entries.append(entry)
        by_path.setdefault(identity(record["path"]), entry)
        if record.get("url"):
            by_url.setdefault(identity(record["url"]), entry)
    pending = list(documents)
    # Older new drafts may reference another document's private audio cache.
    for _ in range(len(pending)+1):
        next_pass = []
        for doc in pending:
            local = identity(doc.get("origin") or doc.get("local_path", ""))
            source = identity(doc.get("source", ""))
            parent = Path(doc.get("local_path", "")).parent.name
            if len(parent) == 32 and parent in {d["id"] for d in pending} and parent != doc["id"] and parent not in by_document:
                next_pass.append(doc)
                continue
            entry = by_path.get(local) or by_url.get(local) or by_url.get(source) or by_document.get(parent)
            if entry is None:
                path = doc.get("local_path", "")
                media_kind = content_kind(doc)
                entry = {"id": "transcript:"+doc["id"], "title": doc["title"], "platform": doc.get("platform", "本地文件"),
                         "kind": media_kind, "path": path, "size": 0, "_record": None,
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
                         "_record": None, "_doc_ids": [doc["id"]], "_search": doc["title"]+" "+document_text(doc), "_created": doc.get("created", 0)}
                entries.append(entry)
            break
        pending = next_pass
    query = query.casefold().strip()
    return sorted((e for e in entries if (not kind or e.get("kind", "video") == kind)
                  and (not has_text or e["_doc_ids"]) and (not query or query in e["_search"].casefold())),
                  key=lambda e: e["_created"], reverse=True)
