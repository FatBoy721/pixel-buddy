"""File index + plain-English query matching. No AI model; just rules.

The index is an in-memory list of every file under the allowed folders
(name, path, modified time). ~100k files is roughly 20 MB of RAM.
"""

import os
import random
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

HOME = Path.home()
DEFAULT_FOLDERS = [HOME / name for name in ("Desktop", "Documents", "Downloads", "OneDrive")]
SKIP_DIRS = {
    "node_modules", "__pycache__", "venv", ".venv", "site-packages", "Library",
    "AppData", "build", "dist", "target", "Pods", "DerivedData",
}
MAX_FILES = 300_000
STALE_AFTER_S = 300

STOPWORDS = {
    "a", "an", "the", "my", "me", "i", "is", "it", "its", "of", "for", "to", "in", "on",
    "at", "and", "or", "where", "whats", "what", "which", "can", "you", "please", "find",
    "show", "get", "grab", "open", "look", "search", "file", "files", "document", "documents",
    "called", "named", "that", "this", "those", "these", "did", "put", "was", "copy",
    "version", "most", "recent", "recently", "latest", "newest", "last", "new", "oldest",
    "old", "first", "from", "with", "about", "some", "any", "all",
}
NEWEST_WORDS = {"recent", "recently", "latest", "newest", "last", "new"}
OLDEST_WORDS = {"oldest", "first", "old"}
RANDOM_WORDS = {"random", "randomly", "any", "anything", "whatever", "surprise"}
BIGGEST_WORDS = {"biggest", "largest", "heaviest"}
SMALLEST_WORDS = {"smallest", "tiniest", "lightest"}
STOPWORDS |= RANDOM_WORDS | BIGGEST_WORDS | SMALLEST_WORDS

SYNONYMS = {
    "resume": ["resume", "cv", "curriculum"],
    "cv": ["resume", "cv", "curriculum"],
    "taxes": ["tax"],
    "tax": ["tax", "w2", "1099"],
    "invoice": ["invoice", "receipt", "bill"],
    "receipt": ["receipt", "invoice"],
    "screenshot": ["screenshot", "screen shot", "capture"],
}

# Things that are almost always documents: rank .pdf/.docx above same-named icons/code.
DOC_EXTS = {".pdf", ".doc", ".docx", ".pages", ".odt", ".rtf", ".txt", ".xlsx", ".csv"}
DOC_WORDS = {"resume", "cv", "tax", "taxes", "invoice", "receipt", "letter", "contract",
             "report", "statement", "application", "form", "paystub", "w2"}

TYPE_WORDS = {
    "pdf": {".pdf"},
    "pdfs": {".pdf"},
    "photo": {".jpg", ".jpeg", ".png", ".heic", ".gif", ".webp"},
    "photos": {".jpg", ".jpeg", ".png", ".heic", ".gif", ".webp"},
    "picture": {".jpg", ".jpeg", ".png", ".heic", ".gif", ".webp"},
    "pictures": {".jpg", ".jpeg", ".png", ".heic", ".gif", ".webp"},
    "image": {".jpg", ".jpeg", ".png", ".heic", ".gif", ".webp", ".svg"},
    "images": {".jpg", ".jpeg", ".png", ".heic", ".gif", ".webp", ".svg"},
    "video": {".mp4", ".mov", ".mkv", ".avi", ".webm"},
    "videos": {".mp4", ".mov", ".mkv", ".avi", ".webm"},
    "song": {".mp3", ".m4a", ".wav", ".flac", ".aac"},
    "music": {".mp3", ".m4a", ".wav", ".flac", ".aac"},
    "spreadsheet": {".xlsx", ".xls", ".csv", ".numbers"},
    "excel": {".xlsx", ".xls", ".csv"},
    "word": {".doc", ".docx", ".pages"},
    "3d": {".3mf", ".stl", ".gcode", ".bgcode", ".obj", ".step", ".stp"},
    "docx": {".doc", ".docx"},
    "slides": {".ppt", ".pptx", ".key"},
    "powerpoint": {".ppt", ".pptx"},
    "zip": {".zip", ".rar", ".7z"},
}


@dataclass(frozen=True)
class Hit:
    path: Path
    mtime: float
    size: int

    @property
    def folder(self):
        return str(self.path.parent)

    @property
    def size_text(self):
        size = float(self.size)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024

    @property
    def breadcrumb(self):
        """Documents → Jobs → 2026 (folder chain relative to home)."""
        try:
            parts = self.path.parent.relative_to(HOME).parts
        except ValueError:
            parts = self.path.parent.parts[1:]
        if len(parts) > 4:
            parts = ("…",) + parts[-3:]
        return " → ".join(parts) or "your home folder"


# "over 2gb", "under 500 MB", "at least 1.5 gigs", "bigger than 10mb", or just "2gb" (= at least).
SIZE_PHRASE = re.compile(
    r"(?P<op>over|above|bigger than|larger than|more than|greater than|at least|>=?|"
    r"under|below|smaller than|less than|at most|<=?)?\s*"
    r"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>tb|gb|mb|kb|gigs?|megs?|g|m|k)\b",
    re.I,
)
UNIT_BYTES = {"k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}
AT_MOST = {"under", "below", "smaller than", "less than", "at most", "<", "<="}


def size_phrase(text):
    """The size filter as the user wrote it ("over 2gb"), or "" if there isn't one."""
    match = SIZE_PHRASE.search(text)
    return match.group(0).strip() if match else ""


def parse_size(text):
    """-> (min_bytes, max_bytes, text without the size phrase). No phrase: (None, None, text)."""
    match = SIZE_PHRASE.search(text)
    if not match:
        return None, None, text
    size = float(match["num"]) * UNIT_BYTES[match["unit"][0].lower()]
    rest = (text[:match.start()] + " " + text[match.end():]).strip()
    if (match["op"] or "").lower() in AT_MOST:
        return None, size, rest
    return size, None, rest


def normalize(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def variants(word):
    """Spellings to accept for one query word: synonyms, and the singular."""
    singular = word[:-1] if len(word) >= 3 and word.endswith("s") and not word.endswith("ss") else word
    return SYNONYMS.get(word) or SYNONYMS.get(singular) or sorted({word, singular})


def matches(variant, name, padded):
    # Short words ("cv", "w2") must start a word so "cv" doesn't hit "rcvd".
    return (" " + variant in padded) if len(variant) <= 3 else variant in name


class FileIndex:
    def __init__(self, folders=None):
        self.folders = [Path(f) for f in (folders or DEFAULT_FOLDERS) if Path(f).is_dir()]
        self.entries = []   # (normalized name, ext, path, mtime, size)
        self.exts = set()   # every extension seen, e.g. ".3mf": lets "3mf" act as a type
        self.built_at = 0.0

    @property
    def stale(self):
        return time.monotonic() - self.built_at > STALE_AFTER_S

    def build(self):
        entries = []
        for root in self.folders:
            for dirpath, dirnames, filenames in os.walk(root, onerror=lambda _e: None):
                dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS]
                for name in filenames:
                    if name.startswith("."):
                        continue
                    path = os.path.join(dirpath, name)
                    try:
                        st = os.stat(path)
                    except OSError:
                        continue
                    stem, ext = os.path.splitext(name)
                    entries.append((normalize(stem), ext.lower(), path, st.st_mtime, st.st_size))
                if len(entries) >= MAX_FILES:
                    break
            if len(entries) >= MAX_FILES:
                break
        self.entries = entries
        self.exts = {ext for _n, ext, _p, _m, _s in entries if ext}
        self.built_at = time.monotonic()
        return self

    def search(self, query, limit=5):
        min_size, max_size, query = parse_size(query)
        words = normalize(query).split()
        wants = set(words)
        oldest = wants & OLDEST_WORDS and not wants & NEWEST_WORDS
        # "3mf", "stl", "pdf"...: any extension on this computer works as a type filter.
        type_words = {w for w in words if w in TYPE_WORDS or "." + w in self.exts}
        exts = set().union(*(TYPE_WORDS.get(w, {"." + w}) for w in type_words))
        terms = [variants(w) for w in words if w not in STOPWORDS and w not in type_words]
        sized = min_size is not None or max_size is not None
        if not terms and not exts and not sized:
            return []

        scored = []
        for name, ext, path, mtime, size in self.entries:
            if exts and ext not in exts:
                continue
            if (min_size is not None and size < min_size) or (max_size is not None and size > max_size):
                continue
            padded = " " + name
            score = sum(any(matches(v, name, padded) for v in t) for t in terms)
            if terms and score == 0:
                continue
            if wants & DOC_WORDS and ext in DOC_EXTS:
                score += 0.5
            scored.append((score, mtime, path, size))

        if not scored:
            return []
        if wants & RANDOM_WORDS:  # "a random 3mf": shuffle among the best matches
            best = max(s[0] for s in scored)
            pool = [s for s in scored if s[0] == best]
            scored = random.sample(pool, min(limit, len(pool)))
        elif wants & BIGGEST_WORDS or wants & SMALLEST_WORDS:
            biggest = bool(wants & BIGGEST_WORDS)
            scored.sort(key=lambda s: (-s[0], -s[3] if biggest else s[3]))
        else:
            sign = 1 if oldest else -1
            scored.sort(key=lambda s: (-s[0], sign * s[1]))
        return [Hit(Path(path), mtime, size) for _score, mtime, path, size in scored[:limit]]
