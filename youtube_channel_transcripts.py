from __future__ import annotations

"""Resumable YouTube Videos and Shorts transcript extractor.

This project keeps this single-channel engine intentionally separate from the
multi-channel scheduler. It uses yt-dlp captions and never bypasses YouTube access
controls. Files are written atomically; manifest state survives interrupted runs.
"""

import csv
import html
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
import textwrap

try:
    import yt_dlp
    from yt_dlp.utils import DownloadError
except ImportError as exc:
    raise SystemExit('yt-dlp is not installed. Run: python -m pip install -r requirements.txt') from exc

PREFERRED_LANGUAGES = ["en", "en-US", "en-GB", "en-IN", "ta", "hi", "te", "ml", "kn", "mr", "bn", "gu", "pa"]
SLEEP_REQUESTS = 2.0
SLEEP_SUBTITLES = 8.0
MIN_SLEEP_BETWEEN_ITEMS = 7.0
MAX_SLEEP_BETWEEN_ITEMS = 14.0
RETRIES = 1
FRAGMENT_RETRIES = 2
SOCKET_TIMEOUT = 45
RATE_LIMIT_BASE_COOLDOWN = 60.0
RATE_LIMIT_MAX_COOLDOWN = 900.0
RATE_LIMIT_MAX_OPERATION_RETRIES = 3
RATE_LIMIT_HARD_PAUSE_AFTER = 3
PROACTIVE_PAUSE_EVERY_OPERATIONS = 8
PROACTIVE_PAUSE_MIN = 30.0
PROACTIVE_PAUSE_MAX = 60.0
CAPTION_FORMAT_PREFERENCE = ["vtt", "srt", "ttml", "srv3", "json3"]
IGNORED_LANGUAGE_KEYS = {"live_chat", "live_comments", "comments", "chat"}
RESERVED_WINDOWS_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
USER_AGENT_OVERRIDE = ""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def explain_error(exc: Exception) -> str:
    message = " ".join(str(exc).split())
    return message[:2000] or exc.__class__.__name__


def is_auth_required(error: object) -> bool:
    """True for a YouTube login/bot challenge; do not repeatedly hammer the endpoint."""
    text = str(error).casefold().replace("’", "'")
    return ("sign in to confirm you're not a bot" in text
            or "confirm you're not a bot" in text
            or "login required" in text)


def clean_name(text: str, max_len: int = 110) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", (text or "Unnamed").strip())
    text = re.sub(r"\s+", " ", text).strip(" .") or "Unnamed"
    if text.upper() in RESERVED_WINDOWS_NAMES:
        text = f"_{text}_"
    return text[:max_len].rstrip(" .") or "Unnamed"


def normalize_channel_url(raw_url: str) -> str:
    url = raw_url.strip()
    if not url:
        raise ValueError("No URL was entered.")
    if url.startswith("@"):
        url = "https://www.youtube.com/" + url
    if "\n" in url or "\r" in url:
        raise ValueError("Paste one channel URL at a time.")
    parts = urlsplit(url if urlsplit(url).scheme else "https://" + url)
    if (parts.hostname or "").lower() not in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        raise ValueError("Expected a YouTube channel URL such as https://www.youtube.com/@handle")
    path = parts.path.rstrip("/") or "/"
    for suffix in ("/videos", "/shorts", "/streams", "/live"):
        if path.lower().endswith(suffix):
            path = path[:-len(suffix)] or "/"
            break
    return urlunsplit(("https", "www.youtube.com", path, "", "")).rstrip("/")


def fallback_folder_name(channel_url: str) -> str:
    token = urlsplit(channel_url).path.strip("/").split("/")[0]
    return clean_name(token[1:] if token.startswith("@") else token or "YouTube Channel")


def video_watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def is_probably_youtube_video_id(value: str | None) -> bool:
    return bool(value and re.fullmatch(r"[A-Za-z0-9_-]{6,20}", value))


def normalize_video_id(entry: dict[str, Any]) -> str | None:
    video_id = entry.get("id")
    if is_probably_youtube_video_id(video_id):
        return str(video_id)
    match = re.search(r"[?&]v=([A-Za-z0-9_-]{6,20})", str(entry.get("url") or entry.get("webpage_url") or ""))
    return match.group(1) if match else None


def available_language_keys(tracks: dict[str, Any]) -> list[str]:
    return [k for k in (tracks or {}) if k.lower() not in IGNORED_LANGUAGE_KEYS and "live_chat" not in k.lower() and "comment" not in k.lower()]


def language_score(language: str) -> tuple[int, int, str]:
    lang = language.lower()
    base = lang.split("-")[0].split("_")[0]
    for index, preferred in enumerate(PREFERRED_LANGUAGES):
        if lang == preferred.lower():
            return (0, index, lang)
    for index, preferred in enumerate(PREFERRED_LANGUAGES):
        if base == preferred.lower().split("-")[0].split("_")[0]:
            return (1, index, lang)
    return (2, 9999, lang)


def pick_format_for_language(track_list: list[dict[str, Any]]) -> str | None:
    formats = list(dict.fromkeys(str(track.get("ext") or "").lower() for track in track_list or []))
    for preferred in CAPTION_FORMAT_PREFERENCE:
        if preferred in formats:
            return preferred
    for track in track_list or []:
        fmt = str(track.get("format") or "").lower()
        for preferred in CAPTION_FORMAT_PREFERENCE:
            if preferred in fmt:
                return preferred
    return None


def normalize_caption_text(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "").replace("\u200b", "").replace("\ufeff", "")).strip()


def strip_vtt_markup(text: str) -> str:
    text = re.sub(r"<\d{1,2}:\d{2}:\d{2}(?:[.,]\d{1,3})?>", "", text)
    text = re.sub(r"</?c(?:\.[^>]*)?>|</?v(?:\s+[^>]*)?>|</?lang(?:\s+[^>]*)?>", "", text)
    return normalize_caption_text(re.sub(r"<[^>]+>", "", text))


def merge_overlapping_cues(cues: list[str]) -> str:
    result: list[str] = []
    for cue in [normalize_caption_text(c) for c in cues if normalize_caption_text(c)]:
        words = cue.split()
        if not result:
            result = words
            continue
        if len(words) <= len(result) and [w.casefold() for w in words] == [w.casefold() for w in result[-len(words):]]:
            continue
        overlap = 0
        for n in range(min(len(words), len(result), 25), 0, -1):
            if [w.casefold() for w in result[-n:]] == [w.casefold() for w in words[:n]]:
                overlap = n
                break
        result.extend(words[overlap:])
    return re.sub(r"\s+", " ", " ".join(result)).strip()


def parse_vtt(data: str) -> str:
    cues, current = [], []
    ignored = False
    time_re = re.compile(r"^\s*(?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{3}\s+-->")
    def flush() -> None:
        nonlocal current
        if current:
            value = strip_vtt_markup(" ".join(current))
            if value:
                cues.append(value)
            current = []
    for raw in data.replace("\ufeff", "").splitlines():
        line = raw.strip()
        if line == "WEBVTT":
            continue
        if line.startswith(("NOTE", "STYLE", "REGION")):
            flush(); ignored = True; continue
        if not line:
            flush(); ignored = False; continue
        if ignored or time_re.match(line) or re.fullmatch(r"\d+", line):
            continue
        current.append(line)
    flush()
    return merge_overlapping_cues(cues)


def parse_srt(data: str) -> str:
    cues, current = [], []
    time_re = re.compile(r"^\s*(?:\d{1,2}:)?\d{2}:\d{2},\d{3}\s+-->")
    for raw in data.replace("\ufeff", "").splitlines() + [""]:
        line = raw.strip()
        if not line:
            if current:
                value = strip_vtt_markup(" ".join(current))
                if value: cues.append(value)
                current = []
        elif time_re.match(line):
            continue
        elif re.fullmatch(r"\d+", line) and not current:
            continue
        else:
            current.append(line)
    return merge_overlapping_cues(cues)


def parse_json3(data: str) -> str:
    payload = json.loads(data)
    cues = []
    for event in payload.get("events", []):
        raw = "".join(str(seg.get("utf8") or "") for seg in event.get("segs") or [])
        if normalize_caption_text(raw): cues.append(raw)
    return merge_overlapping_cues(cues)


def parse_xml_caption(data: str) -> str:
    root = ET.fromstring(data)
    cues = []
    for elem in root.iter():
        if elem.tag.rsplit("}", 1)[-1].lower() not in {"text", "p"}:
            continue
        raw = " ".join(elem.itertext())
        if normalize_caption_text(raw): cues.append(raw)
    return merge_overlapping_cues(cues)


def parse_caption(data: str, ext: str) -> str:
    ext = ext.lower().lstrip(".")
    if ext == "vtt": return parse_vtt(data)
    if ext == "srt": return parse_srt(data)
    if ext == "json3": return parse_json3(data)
    if ext in {"ttml", "srv3", "srv1", "srv2", "xml"}: return parse_xml_caption(data)
    if data.lstrip().startswith("WEBVTT"): return parse_vtt(data)
    if data.lstrip().startswith("{"): return parse_json3(data)
    if data.lstrip().startswith("<"): return parse_xml_caption(data)
    return parse_srt(data)


def format_transcript_for_txt(text: str, width: int = 110) -> str:
    return textwrap.fill(text.strip(), width=width, replace_whitespace=False, break_long_words=False, break_on_hyphens=False) if text.strip() else ""


def write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".part", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content); handle.flush(); os.fsync(handle.fileno())
        Path(temp_name).replace(path)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise


def atomic_json_write(path: Path, payload: Any) -> None:
    write_text_atomic(path, json.dumps(payload, ensure_ascii=False, indent=2))


def atomic_csv_write(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    fields = ["video_id", "type", "title", "url", "status", "source", "language", "filename", "message", "updated_at"]
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".part", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader(); writer.writerows(rows); handle.flush(); os.fsync(handle.fileno())
        Path(temp_name).replace(path)
    except Exception:
        Path(temp_name).unlink(missing_ok=True); raise


def _runtime_version(executable: str) -> tuple[int, ...] | None:
    try:
        result = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=10, check=False)
    except Exception:
        return None
    match = re.search(r"(?:deno|v)?\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?", (result.stdout or result.stderr or "").strip(), re.I)
    return tuple(int(x or 0) for x in match.groups()) if match else None


def find_js_runtime() -> tuple[str | None, str | None, str | None]:
    for name in ("deno", "node"):
        path = shutil.which(name)
        if path:
            version = _runtime_version(path)
            minimum = (2, 3, 0) if name == "deno" else (22, 0, 0)
            if version and version >= minimum:
                return name, path, ""
    return None, None, "Install Deno 2.3+ or Node.js 22+ for current yt-dlp YouTube support."


def ensure_yt_dlp_components() -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec("yt_dlp_ejs") is not None
    except (ImportError, ValueError):
        return False


class RateLimitManager:
    def __init__(self, state_path: Path):
        self.state_path = state_path
        self.state = self._load()
        self.last_operation_at = 0.0
        self.run_429_events = 0
        self.run_cooldowns = 0
        self.successful_operations = 0

    def _load(self) -> dict[str, Any]:
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return {"cooldown_until": float(data.get("cooldown_until", 0) or 0), "consecutive_429": int(data.get("consecutive_429", 0) or 0), "total_429_events": int(data.get("total_429_events", 0) or 0), "last_429_at": str(data.get("last_429_at", "") or "")}
            except Exception:
                pass
        return {"cooldown_until": 0.0, "consecutive_429": 0, "total_429_events": 0, "last_429_at": ""}

    def _save(self) -> None:
        atomic_json_write(self.state_path, self.state)

    @staticmethod
    def is_rate_limited(exc: Exception) -> bool:
        text = str(exc).lower()
        return getattr(exc, "status", None) == 429 or "429" in text and any(x in text for x in ("http error", "too many requests", "status code"))

    def _polite_delay(self) -> None:
        remaining = random.uniform(MIN_SLEEP_BETWEEN_ITEMS, MAX_SLEEP_BETWEEN_ITEMS) - (time.monotonic() - self.last_operation_at)
        if remaining > 0: time.sleep(remaining)
        self.last_operation_at = time.monotonic()

    def wait_if_blocked(self, reason: str = "") -> None:
        while True:
            remaining = float(self.state.get("cooldown_until", 0) or 0) - time.time()
            if remaining <= 0: return
            self.run_cooldowns += 1
            print(f"YouTube 429 cooldown ({reason}); waiting {int(remaining + .999)}s", flush=True)
            time.sleep(min(20.0, remaining))

    def note_success(self) -> None:
        self.successful_operations += 1
        changed = self.state.get("consecutive_429", 0) != 0 or float(self.state.get("cooldown_until", 0) or 0) != 0
        self.state["consecutive_429"] = 0; self.state["cooldown_until"] = 0.0
        if changed: self._save()
        if self.successful_operations % PROACTIVE_PAUSE_EVERY_OPERATIONS == 0:
            time.sleep(random.uniform(PROACTIVE_PAUSE_MIN, PROACTIVE_PAUSE_MAX))

    def note_429(self, context: str) -> float:
        consecutive = int(self.state.get("consecutive_429", 0) or 0) + 1
        total = int(self.state.get("total_429_events", 0) or 0) + 1
        delay = min(RATE_LIMIT_MAX_COOLDOWN, max(600.0 if consecutive >= RATE_LIMIT_HARD_PAUSE_AFTER else 0.0, RATE_LIMIT_BASE_COOLDOWN * (2 ** (consecutive - 1))))
        delay = min(RATE_LIMIT_MAX_COOLDOWN, delay * random.uniform(.9, 1.2))
        self.state.update({"cooldown_until": time.time() + delay, "consecutive_429": consecutive, "total_429_events": total, "last_429_at": utc_now()})
        self._save(); self.run_429_events += 1
        print(f"HTTP 429 during {context}; cooldown {int(delay)}s", flush=True)
        return delay

    def run(self, operation, *, context: str, max_attempts: int = RATE_LIMIT_MAX_OPERATION_RETRIES):
        last_exc = None
        for attempt in range(1, max_attempts + 1):
            self.wait_if_blocked(context); self._polite_delay()
            try:
                value = operation(); self.note_success(); return value
            except Exception as exc:
                last_exc = exc
                if not self.is_rate_limited(exc): raise
                self.note_429(context)
                if attempt >= max_attempts: break
        raise last_exc or RuntimeError("Rate-limited operation failed")


def base_ydl_params(browser: str | None, runtime_name: str | None, runtime_path: str | None,
                    remote_components: set[str] | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {"quiet": True, "no_warnings": True, "noprogress": True, "ignoreerrors": False,
        "retries": RETRIES, "fragment_retries": FRAGMENT_RETRIES, "extractor_retries": RETRIES,
        "socket_timeout": SOCKET_TIMEOUT, "sleep_interval_requests": SLEEP_REQUESTS,
        "sleep_interval": 2.0, "max_sleep_interval": 5.0,
        "extractor_args": {"youtube": {"skip": ["translated_subs"]}}}
    if browser:
        params["cookiesfrombrowser"] = (browser,)
    # GitHub-hosted runners can be challenged even while public channel tabs
    # remain visible. Accept only a user-supplied authorized Netscape cookie file;
    # never embed credentials in the repository or try to bypass access controls.
    cookie_file = os.getenv("YOUTUBE_COOKIES_FILE", "").strip()
    if cookie_file and Path(cookie_file).is_file():
        params["cookiefile"] = cookie_file
    if USER_AGENT_OVERRIDE:
        params["http_headers"] = {"User-Agent": USER_AGENT_OVERRIDE, "Accept-Language": "en-US,en;q=0.9"}
    if runtime_name and runtime_path:
        params["js_runtimes"] = {runtime_name: {"executable": runtime_path}}
    if remote_components:
        params["remote_components"] = set(remote_components)
    return params


def discover_channel(channel_url: str, browser: str | None, runtime_name: str | None,
                     runtime_path: str | None, remote_components: set[str], rate_limiter: RateLimitManager):
    found: dict[str, dict[str, Any]] = {}
    scan_results: list[dict[str, Any]] = []
    channel_name = None; channel_id = None; failed_kinds: set[str] = set()
    class CaptureLogger:
        def __init__(self) -> None:
            self.errors: list[str] = []
        def debug(self, message: str) -> None:
            pass
        def warning(self, message: str) -> None:
            pass
        def error(self, message: str) -> None:
            self.errors.append(str(message))

    scan_logger = CaptureLogger()
    params = {**base_ydl_params(browser, runtime_name, runtime_path, remote_components), "extract_flat": True,
              "ignoreerrors": True, "playlistend": None, "logger": scan_logger}

    def consume(info: dict[str, Any], page_url: str, kind: str) -> tuple[int, int]:
        nonlocal channel_name, channel_id
        page_channel_id = info.get("channel_id")
        raw_id = str(info.get("id") or "")
        if not page_channel_id and raw_id.startswith("UC") and len(raw_id) >= 20: page_channel_id = raw_id
        if page_channel_id: channel_id = str(page_channel_id)
        candidate_name = info.get("uploader") or info.get("channel") or info.get("title")
        if candidate_name:
            candidate_name = re.sub(r"\s+-\s+(Videos|Shorts)$", "", str(candidate_name), flags=re.I).strip()
            if candidate_name.lower() not in {"videos", "shorts", "channel"}: channel_name = channel_name or candidate_name
        page_entries = list(info.get("entries") or [])
        new_count = 0; unusable = 0
        for entry in page_entries:
            if not entry: unusable += 1; continue
            vid = normalize_video_id(entry)
            if not vid: unusable += 1; continue
            item_kind = "SHORT" if kind == "SHORT" else "VIDEO"
            if vid not in found:
                found[vid] = {"id": vid, "url": entry.get("webpage_url") or video_watch_url(vid),
                    "title": str(entry.get("title") or vid), "kind": item_kind,
                    "channel": entry.get("channel") or entry.get("uploader") or channel_name,
                    "index_hint": len(found) + 1, "upload_date": entry.get("upload_date")}
                new_count += 1
            elif item_kind == "SHORT": found[vid]["kind"] = "SHORT"
        scan_results.append({"type": kind, "url": page_url, "status": "OK", "discovered": len(page_entries),
            "new_items": new_count, "unusable_entries": unusable, "reported_playlist_count": info.get("playlist_count"), "channel_id": channel_id})
        return len(page_entries), new_count

    pages = [(channel_url, "CHANNEL"), (channel_url.rstrip("/") + "/videos", "VIDEO"), (channel_url.rstrip("/") + "/shorts", "SHORT")]
    with yt_dlp.YoutubeDL(params) as ydl:
        def extract_page(page_url: str, context: str) -> dict[str, Any]:
            scan_logger.errors.clear()
            info = rate_limiter.run(lambda: ydl.extract_info(page_url, download=False), context=context)
            if not info:
                details = " | ".join(scan_logger.errors[-3:])
                raise DownloadError(details or "yt-dlp returned no data")
            return info

        for page_url, kind in pages:
            print(f"Scanning {kind}: {page_url}", flush=True)
            try:
                info = extract_page(page_url, f"channel scan: {kind}")
                count, new_count = consume(info, page_url, kind)
                print(f"Found {new_count} new item(s); {count} entries returned.", flush=True)
            except Exception as exc:
                message = explain_error(exc)
                # Some channels genuinely have no Shorts tab. Record that explicitly
                # and do not let an absent optional tab block a valid full backfill.
                if kind == "SHORT" and "does not have a shorts tab" in message.casefold():
                    scan_results.append({"type": kind, "url": page_url, "status": "NO_TAB", "message": message})
                    print(f"Shorts tab not present; continuing with videos: {page_url}", flush=True)
                    continue
                # The channel root is a useful fallback, not a required source
                # when the /videos and /shorts tabs can be enumerated directly.
                if kind in {"VIDEO", "SHORT"}:
                    failed_kinds.add(kind)
                scan_results.append({"type": kind, "url": page_url, "status": "FAILED", "message": message})
                print(f"Scan failed: {message}", flush=True)
        if channel_id and channel_id.startswith("UC"):
            canonical = f"https://www.youtube.com/channel/{channel_id}"
            for kind, suffix in (("VIDEO", "/videos"), ("SHORT", "/shorts")):
                if kind not in failed_kinds: continue
                retry_url = canonical + suffix
                try:
                    info = extract_page(retry_url, f"channel retry: {kind}")
                    consume(info, retry_url, kind + "_ID_RETRY"); failed_kinds.discard(kind)
                except Exception as exc:
                    scan_results.append({"type": kind + "_ID_RETRY", "url": retry_url, "status": "FAILED", "message": explain_error(exc)})
            if not any(r.get("type") in {"VIDEO", "VIDEO_ID_RETRY"} and r.get("status") == "OK" and r.get("discovered", 0) > 0 for r in scan_results):
                upload_id = "UU" + channel_id[2:]
                url = f"https://www.youtube.com/playlist?list={upload_id}"
                try:
                    info = extract_page(url, "uploads playlist fallback")
                    consume(info, url, "UPLOADS_FALLBACK"); failed_kinds.discard("VIDEO")
                except Exception as exc:
                    scan_results.append({"type": "UPLOADS_FALLBACK", "url": url, "status": "FAILED", "message": explain_error(exc)})
    if not found:
        details = [f"{r.get('type')}: {r.get('message', 'no entries')}" for r in scan_results if r.get("status") == "FAILED"]
        raise DownloadError("Channel enumeration produced 0 usable items. " + " | ".join(details[:6]))
    fatal = []
    for kind in sorted(failed_kinds):
        messages = [str(r.get("message")) for r in scan_results if r.get("type") == kind and r.get("status") == "FAILED"]
        fatal.append(f"{kind}: {messages[-1] if messages else 'scan failed'}")
    return channel_name, list(found.values()), scan_results, fatal


def get_full_video_info(item: dict[str, Any], browser: str | None, runtime_name: str | None,
                        runtime_path: str | None, remote_components: set[str], rate_limiter: RateLimitManager) -> dict[str, Any]:
    params = {**base_ydl_params(browser, runtime_name, runtime_path, remote_components), "skip_download": True, "noplaylist": True}
    with yt_dlp.YoutubeDL(params) as ydl:
        info = rate_limiter.run(lambda: ydl.extract_info(item["url"], download=False), context=f"metadata: {item['id']}")
    if not info: raise DownloadError("Could not obtain video metadata")
    return info


def _original_language_candidates(info: dict[str, Any], tracks: dict[str, Any]) -> list[str]:
    keys = available_language_keys(tracks)
    orig = [k for k in keys if k.lower().endswith("-orig")]
    if orig: return sorted(orig, key=language_score)
    reported = str(info.get("language") or info.get("original_language") or info.get("language_code") or "").lower()
    base = reported.split("-")[0].split("_")[0]
    matches = [k for k in keys if k.lower().split("-")[0].split("_")[0] == base and not k.lower().endswith("-orig")] if base else []
    return sorted(matches, key=language_score)


def subtitle_candidates(info: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    manual = info.get("subtitles") or {}
    for lang in sorted(available_language_keys(manual), key=language_score):
        fmt = pick_format_for_language(manual.get(lang) or [])
        if fmt: result.append({"source": "manual", "is_auto": False, "language": lang, "format": fmt})
    automatic = info.get("automatic_captions") or {}
    for lang in _original_language_candidates(info, automatic):
        fmt = pick_format_for_language(automatic.get(lang) or [])
        if fmt: result.append({"source": "automatic", "is_auto": True, "language": lang, "format": fmt})
    return result


def choose_caption_candidates(info: dict[str, Any]) -> list[dict[str, Any]]:
    return subtitle_candidates(info)


def temp_subtitle_download(item: dict[str, Any], candidate: dict[str, Any], output_dir: Path,
                           browser: str | None, runtime_name: str | None, runtime_path: str | None,
                           remote_components: set[str], rate_limiter: RateLimitManager) -> tuple[str, str]:
    vid = item["id"]
    with tempfile.TemporaryDirectory(prefix=f"_{vid}_caps_", dir=str(output_dir)) as tmp:
        outtmpl = str(Path(tmp) / "%(id)s.%(ext)s")
        params = {**base_ydl_params(browser, runtime_name, runtime_path, remote_components), "skip_download": True,
            "writesubtitles": not candidate["is_auto"], "writeautomaticsub": candidate["is_auto"],
            "subtitleslangs": [candidate["language"]], "subtitlesformat": candidate["format"], "outtmpl": outtmpl,
            "sleep_interval_subtitles": SLEEP_SUBTITLES, "overwrites": True, "ignoreerrors": False}
        with yt_dlp.YoutubeDL(params) as ydl:
            rate_limiter.run(lambda: ydl.download([item["url"]]), context=f"subtitle {candidate['language']} for {vid}")
        matches = list(Path(tmp).glob(f"{vid}*.{candidate['format']}"))
        if not matches:
            matches = [p for p in Path(tmp).iterdir() if p.is_file() and p.suffix.lower().lstrip(".") in {"vtt", "srt", "ttml", "xml", "srv3", "srv1", "srv2", "json3"}]
        if not matches: raise DownloadError(f"yt-dlp completed but no {candidate['format']} subtitle appeared")
        path = matches[0]
        return path.read_text(encoding="utf-8", errors="replace"), path.suffix


def build_transcript_from_youtube_captions(item: dict[str, Any], info: dict[str, Any], output_dir: Path,
        browser: str | None, runtime_name: str | None, runtime_path: str | None,
        remote_components: set[str], rate_limiter: RateLimitManager) -> tuple[str, str, str]:
    candidates = choose_caption_candidates(info)
    if not candidates: raise LookupError("No parseable YouTube caption tracks were advertised")
    errors = []
    for candidate in candidates:
        try:
            raw, ext = temp_subtitle_download(item, candidate, output_dir, browser, runtime_name, runtime_path, remote_components, rate_limiter)
            text = parse_caption(raw, ext)
            if not text: raise ValueError("Downloaded captions were empty after parsing")
            return text, candidate["language"], "YouTube automatic captions" if candidate["is_auto"] else "YouTube subtitles"
        except Exception as exc:
            errors.append(f"{candidate['source']}:{candidate['language']}:{candidate['format']} -> {exc}")
            if RateLimitManager.is_rate_limited(exc): break
    raise DownloadError("All attempted caption tracks failed. " + " | ".join(errors[:5]))


def whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def load_whisper_model(model_name: str):
    from faster_whisper import WhisperModel
    print(f"Loading Whisper model {model_name} (first run may download it)...", flush=True)
    return WhisperModel(model_name, device="auto", compute_type="auto")


def whisper_download_audio(item: dict[str, Any], output_dir: Path, browser: str | None,
        runtime_name: str | None, runtime_path: str | None, remote_components: set[str],
        rate_limiter: RateLimitManager) -> Path:
    vid = item["id"]
    tmp = Path(tempfile.mkdtemp(prefix=f"_{vid}_audio_", dir=str(output_dir)))
    try:
        params = {**base_ydl_params(browser, runtime_name, runtime_path, remote_components), "format": "bestaudio/best",
            "outtmpl": str(tmp / f"{vid}.%(ext)s"), "noplaylist": True, "overwrites": True, "ignoreerrors": False}
        with yt_dlp.YoutubeDL(params) as ydl:
            rate_limiter.run(lambda: ydl.download([item["url"]]), context=f"audio: {vid}")
        files = [p for p in tmp.iterdir() if p.is_file()]
        if not files: raise DownloadError("Audio download completed but no audio file appeared")
        return files[0]
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True); raise


def transcribe_with_whisper(item: dict[str, Any], output_dir: Path, model, browser: str | None,
        runtime_name: str | None, runtime_path: str | None, remote_components: set[str],
        rate_limiter: RateLimitManager) -> tuple[str, str, str]:
    audio_path = whisper_download_audio(item, output_dir, browser, runtime_name, runtime_path, remote_components, rate_limiter)
    try:
        segments, info = model.transcribe(str(audio_path), vad_filter=True, condition_on_previous_text=True)
        text = merge_overlapping_cues([normalize_caption_text(seg.text) for seg in segments])
        if not text: raise RuntimeError("Whisper produced an empty transcript")
        return text, str(getattr(info, "language", None) or "auto-detected"), "Local faster-whisper"
    finally:
        shutil.rmtree(audio_path.parent, ignore_errors=True)


def find_existing_channel_folder(script_dir: Path, channel_url: str) -> Path | None:
    preferred = script_dir / fallback_folder_name(channel_url)
    if (preferred / "transcript_manifest.json").is_file(): return preferred
    target = normalize_channel_url(channel_url).lower()
    for folder in script_dir.iterdir():
        summary = folder / "collection_summary.txt"
        if folder.is_dir() and (folder / "transcript_manifest.json").is_file() and summary.is_file():
            try:
                for line in summary.read_text(encoding="utf-8", errors="replace").lower().splitlines():
                    if line.startswith("channel url:") and line.split(":", 1)[1].strip() == target: return folder
            except OSError: pass
    return None


def load_manifest(path: Path) -> dict[str, dict[str, Any]]:
    if path.exists():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict): return value
        except Exception:
            print(f"Warning: manifest {path.name} could not be read", flush=True)
    return {}


def find_existing_transcript(output_dir: Path, video_id: str) -> Path | None:
    matches = [p for p in output_dir.glob("*.txt") if p.name.endswith(f"[{video_id}].txt") and p.stat().st_size > 100]
    return max(matches, key=lambda p: p.stat().st_mtime) if matches else None


def seed_manifest_from_entries(manifest_path: Path, manifest: dict[str, dict[str, Any]], entries: list[dict[str, Any]]) -> None:
    changed = False
    for item in entries:
        vid = item.get("id")
        if not vid: continue
        if vid in manifest:
            existing = manifest[vid]
            merged = {**existing, "video_id": vid, "type": item.get("kind", existing.get("type", "VIDEO")),
                "title": item.get("title") or existing.get("title") or vid, "url": item.get("url") or existing.get("url") or video_watch_url(vid),
                "channel": item.get("channel") or existing.get("channel") or "Unknown", "last_discovered_at": utc_now()}
            if merged != existing: manifest[vid] = merged; changed = True
        else:
            manifest[vid] = {"video_id": vid, "type": item.get("kind", "VIDEO"), "title": item.get("title") or vid,
                "url": item.get("url") or video_watch_url(vid), "channel": item.get("channel") or "Unknown", "status": "DISCOVERED",
                "source": "", "language": "", "filename": "", "message": "Discovered; waiting for transcript",
                "discovered_at": utc_now(), "last_discovered_at": utc_now(), "updated_at": utc_now()}
            changed = True
    if changed: atomic_json_write(manifest_path, manifest)


def merge_pending_manifest_entries(entries: list[dict[str, Any]], manifest: dict[str, dict[str, Any]],
                                   output_dir: Path | None = None) -> list[dict[str, Any]]:
    """Combine the latest channel scan with unresolved manifest items.

    A record marked SAVED is skipped only if its transcript still exists and is
    non-empty. This recovers a manifest/file mismatch instead of leaving the
    channel permanently incomplete after a deleted or corrupted transcript.
    """
    by_id = {item["id"]: item for item in entries if item.get("id")}
    for vid, record in manifest.items():
        if not isinstance(record, dict) or not is_probably_youtube_video_id(vid) or vid in by_id:
            continue
        saved_file_ok = False
        filename = str(record.get("filename") or "")
        if record.get("status") == "SAVED" and output_dir is not None and filename and Path(filename).name == filename:
            candidate = output_dir / filename
            saved_file_ok = candidate.is_file() and candidate.stat().st_size > 100
        if record.get("status") == "SAVED" and (output_dir is None or saved_file_ok):
            continue
        by_id[vid] = {"id": vid, "url": record.get("url") or video_watch_url(vid), "title": record.get("title") or vid,
            "kind": record.get("type") or "VIDEO", "channel": record.get("channel") or "Unknown", "resume_from_manifest": True}
    return list(by_id.values())


def update_manifest(manifest_path: Path, manifest: dict[str, dict[str, Any]], item: dict[str, Any], *, status: str,
                    source: str = "", language: str = "", filename: str = "", message: str = "") -> None:
    existing = manifest.get(item["id"], {})
    manifest[item["id"]] = {**existing, "video_id": item["id"], "type": item.get("kind", "VIDEO"),
        "title": item.get("title") or item["id"], "url": item.get("url") or video_watch_url(item["id"]),
        "channel": item.get("channel") or "Unknown", "status": status, "source": source, "language": language,
        "filename": filename, "message": message, "updated_at": utc_now()}
    atomic_json_write(manifest_path, manifest)


def manifest_rows(manifest: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"video_id": v.get("video_id", ""), "type": v.get("type", ""), "title": v.get("title", ""),
        "url": v.get("url", ""), "status": v.get("status", ""), "source": v.get("source", ""),
        "language": v.get("language", ""), "filename": v.get("filename", ""), "message": v.get("message", ""),
        "updated_at": v.get("updated_at", "")} for v in manifest.values()]


def write_summary(path: Path, *, channel_name: str, channel_url: str, entries: list[dict[str, Any]],
                  scan_results: list[dict[str, Any]], fatal_scan_errors: list[str], manifest: dict[str, dict[str, Any]],
                  whisper_mode: bool, rate_limiter: RateLimitManager) -> None:
    counts = {state: sum(1 for item in manifest.values() if item.get("status") == state) for state in ("SAVED", "NO_CAPTIONS", "FAILED", "AUTH_REQUIRED", "RATE_LIMITED", "DISCOVERED")}
    lines = [f"Channel name: {channel_name}", f"Channel URL: {normalize_channel_url(channel_url)}", f"Last updated UTC: {utc_now()}",
        f"Discovered in current scan: {len(entries)}", f"Manifest total: {len(manifest)}", f"Transcripts saved: {counts['SAVED']}",
        f"No captions: {counts['NO_CAPTIONS']}", f"Failures: {counts['FAILED']}", f"Authentication required: {counts['AUTH_REQUIRED']}", f"Rate limited: {counts['RATE_LIMITED']}",
        f"Still discovered/pending: {counts['DISCOVERED']}", f"Whisper fallback enabled: {whisper_mode}",
        f"HTTP 429 events this run: {rate_limiter.run_429_events}", "", "Scan results:"]
    lines.extend(f"- {r.get('type')}: {r.get('status')} — {r.get('url')} {r.get('message', '')}" for r in scan_results)
    if fatal_scan_errors: lines.extend(["", "Scan errors:", *[f"- {e}" for e in fatal_scan_errors]])
    write_text_atomic(path, "\n".join(lines) + "\n")


def safe_title_filename(title: str, video_id: str, kind: str) -> str:
    prefix, suffix = f"{kind} - ", f" [{video_id}].txt"
    available = max(12, 180 - len(prefix) - len(suffix))
    return f"{prefix}{clean_name(title, available)}{suffix}"


def item_has_saved_transcript(item: dict[str, Any], manifest: dict[str, dict[str, Any]], output_dir: Path) -> Path | None:
    record = manifest.get(item["id"], {})
    filename = record.get("filename")
    if record.get("status") == "SAVED" and filename:
        path = output_dir / filename
        if path.is_file() and path.stat().st_size > 100: return path
    return find_existing_transcript(output_dir, item["id"])


def process_item(item: dict[str, Any], output_dir: Path, manifest: dict[str, dict[str, Any]], manifest_path: Path,
                 browser: str | None, runtime_name: str | None, runtime_path: str | None, remote_components: set[str],
                 use_whisper: bool, whisper_model, rate_limiter: RateLimitManager) -> tuple[bool, str]:
    vid = item["id"]
    try:
        existing = item_has_saved_transcript(item, manifest, output_dir)
        if existing:
            update_manifest(manifest_path, manifest, item, status="SAVED", filename=existing.name, message="Recovered existing transcript",
                source=manifest.get(vid, {}).get("source", "Existing transcript"), language=manifest.get(vid, {}).get("language", ""))
            return True, f"already saved: {existing.name}"
        info = get_full_video_info(item, browser, runtime_name, runtime_path, remote_components, rate_limiter)
        try:
            text, language, source = build_transcript_from_youtube_captions(item, info, output_dir, browser, runtime_name, runtime_path, remote_components, rate_limiter)
        except Exception as caption_exc:
            if not use_whisper or whisper_model is None:
                status = ("AUTH_REQUIRED" if is_auth_required(caption_exc) else
                          "RATE_LIMITED" if RateLimitManager.is_rate_limited(caption_exc) else
                          "NO_CAPTIONS" if isinstance(caption_exc, LookupError) else "FAILED")
                update_manifest(manifest_path, manifest, item, status=status, message=explain_error(caption_exc))
                return False, explain_error(caption_exc)
            text, language, source = transcribe_with_whisper(item, output_dir, whisper_model, browser, runtime_name, runtime_path, remote_components, rate_limiter)
        filename = safe_title_filename(str(item.get("title") or info.get("title") or vid), vid, str(item.get("kind") or "VIDEO"))
        body = f"Title: {item.get('title') or info.get('title') or vid}\nChannel: {item.get('channel') or info.get('channel') or info.get('uploader') or 'Unknown'}\nType: {item.get('kind') or 'VIDEO'}\nVideo ID: {vid}\nURL: {item.get('url') or video_watch_url(vid)}\nLanguage: {language}\nTranscript source: {source}\nCollected UTC: {utc_now()}\n\n{format_transcript_for_txt(text)}\n"
        write_text_atomic(output_dir / filename, body)
        update_manifest(manifest_path, manifest, item, status="SAVED", source=source, language=language, filename=filename, message="Transcript saved")
        return True, filename
    except Exception as exc:
        status = ("AUTH_REQUIRED" if is_auth_required(exc) else
                  "RATE_LIMITED" if RateLimitManager.is_rate_limited(exc) else "FAILED")
        update_manifest(manifest_path, manifest, item, status=status, message=explain_error(exc))
        return False, explain_error(exc)


def main() -> None:
    print("YouTube Channel → Video + Shorts Transcript Collector")
    print("Use multi_channel_runner.py for scheduled multi-channel operation.")
    channel_url = normalize_channel_url(input("Paste the YouTube channel link: ").strip())
    choice = input("Use local faster-whisper fallback? [y/N]: ").strip().lower()
    use_whisper = choice in {"y", "yes"}
    whisper_model_name = input("Whisper model [small]: ").strip() or "small" if use_whisper else "small"
    browser_choice = input("Browser cookies (0 none, 1 Chrome, 2 Edge, 3 Firefox, 4 Brave) [0]: ").strip()
    browser = {"1": "chrome", "2": "edge", "3": "firefox", "4": "brave"}.get(browser_choice)
    script_dir = Path(__file__).resolve().parent
    runtime_name, runtime_path, warning = find_js_runtime()
    if not runtime_name: raise RuntimeError(warning or "JavaScript runtime is required")
    remote = set() if ensure_yt_dlp_components() else {"ejs:github"}
    rate = RateLimitManager(script_dir / ".youtube_rate_limit_state.json")
    rate.wait_if_blocked("previous run cooldown")
    name, entries, scans, errors = discover_channel(channel_url, browser, runtime_name, runtime_path, remote, rate)
    name = clean_name(name or fallback_folder_name(channel_url))
    folder = script_dir / name; folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / "transcript_manifest.json"; manifest = load_manifest(manifest_path)
    seed_manifest_from_entries(manifest_path, manifest, entries); entries = merge_pending_manifest_entries(entries, manifest)
    model = load_whisper_model(whisper_model_name) if use_whisper and whisper_available() else None
    for i, item in enumerate(entries, 1):
        if item_has_saved_transcript(item, manifest, folder): continue
        print(f"[{i}/{len(entries)}] {item.get('title', item['id'])}")
        process_item(item, folder, manifest, manifest_path, browser, runtime_name, runtime_path, remote, bool(model), model, rate)
        time.sleep(random.uniform(MIN_SLEEP_BETWEEN_ITEMS, MAX_SLEEP_BETWEEN_ITEMS))
    atomic_csv_write(folder / "transcript_audit.csv", manifest_rows(manifest))
    write_summary(folder / "collection_summary.txt", channel_name=name, channel_url=channel_url, entries=entries,
        scan_results=scans, fatal_scan_errors=errors, manifest=manifest, whisper_mode=bool(model), rate_limiter=rate)
    print(f"Saved transcripts to {folder}")


if __name__ == "__main__":
    main()
