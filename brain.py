"""The crab's brain: turns a chat message into what he should do.

Every brain returns a Decision:
    chat        just talk back (Decision.text)
    find_files  go fetch a file (Decision.query), saying Decision.text first
    web_search  go search the web (Decision.query), saying Decision.text first

RuleBrain is the always-available fallback (keyword rules, no AI). The local
model brain plugs in behind the same decide() call.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass

from lines import line
from search import BIGGEST_WORDS, NEWEST_WORDS, OLDEST_WORDS, RANDOM_WORDS, SMALLEST_WORDS, size_phrase
from web import split_web_prefix


@dataclass(frozen=True)
class Decision:
    action: str          # "chat" | "find_files" | "web_search"
    text: str = ""       # what he says in the chat
    query: str = ""      # search terms for find_files / web_search


FILE_HINTS = re.compile(
    r"\b(where('?s| is| are| did)|find|locate|open|grab|fetch|get me|bring me|pull up)\b"
    r"|\b(file|files|folder|pdf|docx?|resume|cv|photo|picture|screenshot|video|3mf|stl|gcode|zip|download(ed|s)?)\b"
    r"|\.\w{2,5}\b",
    re.I,
)
# A clear "go get me a file" request, e.g. "grab any stl", "find a random 3mf".
FETCH_REQUEST = re.compile(
    r"\b(find|grab|get|fetch|bring|pull up|show me|open|dig up)\b.*"
    r"\b(file|files|3mf|stl|gcode|bgcode|obj|step|pdf|docx?|photo|picture|image|video|zip|iso|resume)\b",
    re.I,
)
SORT_WORDS = RANDOM_WORDS | BIGGEST_WORDS | SMALLEST_WORDS | NEWEST_WORDS | OLDEST_WORDS
WEB_HINTS = re.compile(r"\b(google|look up|search (the )?(web|online|internet)|on the web|online)\b", re.I)
FILLER = re.compile(
    r"\b(hey|yo|crab|buddy|please|pls|can you|could you|would you|will you|i need|i want|go|for me|"
    r"where('?s| is| are| did i put)|find|locate|open|grab|fetch|get me|bring me|pull up|show me)\b",
    re.I,
)


class RuleBrain:
    """No AI: keyword rules. Used when the local model isn't available."""

    name = "rules"

    def decide(self, history, spicy=False):
        text = history[-1]["content"].strip()
        stripped, prefixed = split_web_prefix(text)
        if prefixed or WEB_HINTS.search(text):
            query = WEB_HINTS.sub("", stripped).strip(" ?.!") or stripped
            return Decision("web_search", line("go_web", spicy), query)
        if FILE_HINTS.search(text):
            query = FILLER.sub(" ", text).strip(" ?.!")
            return Decision("find_files", line("go_files", spicy), query or text)
        return Decision("chat", line("no_brain", spicy))


# --- local AI (Ollama) --------------------------------------------------------

OLLAMA = "http://127.0.0.1:11434"
HISTORY_LIMIT = 16  # messages sent to the model (keeps it fast on weak machines)

PERSONA = """You are Crab, a tiny pixel-art crab who lives on the user's desktop.
You're a little grumpy, very loyal, funny, and you keep replies SHORT (1-3 sentences).
{voice}

You can do two things with tools:
- find_files: search the user's computer for a file. Use it whenever they want a file,
  document, photo, download, 3D print file (3mf, stl, gcode), or ask where something is,
  including "a random ___" or "any ___". Put only the important words
  in the query (e.g. "most recent resume", "benchy 3mf", "tax pdf 2025").
- web_search: search the internet. Use it ONLY when the user asks you to look something
  up / search / google it, or says yes after you offered.

For general questions, just answer from what you know. If the answer depends on
current or online info (news, prices, weather, product specs, sports), answer briefly
if you can and then offer: "Want me to dig on the web?"
Never make up file names or paths; use find_files."""

VOICES = {
    True: "You swear a lot, casually and creatively (fuck, shit, damn, hell), roasting the user "
          "affectionately. Never hateful or slurs. Never say 'goddamn', 'God', or 'Jesus Christ'.",
    False: "You never swear or say 'God' / 'Jesus'. You're sassy but clean.",
}

TOOLS = [
    {"type": "function", "function": {
        "name": "find_files",
        "description": "Search the user's computer for files by name.",
        "parameters": {"type": "object", "required": ["query"], "properties": {
            "query": {"type": "string", "description": "Key words from the file name. ALWAYS keep the user's "
                      "words like random, any, biggest, smallest, newest, oldest, size limits like 'over 2gb' or "
                      "'under 10mb', and file types like 3mf, stl, gcode, pdf, photo. e.g. 'random 3mf', "
                      "'biggest stl', 'random over 2gb'."},
            "say": {"type": "string", "description": "Short in-character line to say while you go look."},
        }},
    }},
    {"type": "function", "function": {
        "name": "web_search",
        "description": "Search the internet.",
        "parameters": {"type": "object", "required": ["query"], "properties": {
            "query": {"type": "string", "description": "The web search query."},
            "say": {"type": "string", "description": "Short in-character line to say while you go look."},
        }},
    }},
]


def ollama(path, payload=None, timeout=120):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(OLLAMA + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def installed_models():
    """Names of models Ollama has, or [] if Ollama isn't running."""
    try:
        return [m["name"] for m in ollama("/api/tags", timeout=2)["models"]]
    except (OSError, ValueError, KeyError):
        return []


class OllamaBrain:
    """A small local model that chats in character and picks tools."""

    def __init__(self, model):
        self.model = model
        self.name = model

    def _chat(self, messages, spicy, tools=True):
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": PERSONA.format(voice=VOICES[spicy])}] + messages,
            "stream": False,
            "think": False,          # skip hidden reasoning: much faster on small models
            "keep_alive": "15m",
            "options": {"temperature": 0.7, "num_ctx": 4096},
        }
        if tools:
            payload["tools"] = TOOLS
        return ollama("/api/chat", payload)["message"]

    def decide(self, history, spicy=False):
        asked = history[-1]["content"]
        message = self._chat(history[-HISTORY_LIMIT:], spicy)
        text = strip_think(message.get("content", ""))
        for call in message.get("tool_calls") or []:
            fn = call.get("function", {})
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                args = json.loads(args or "{}")
            name = fn.get("name")
            if name in ("find_files", "web_search") and args.get("query"):
                say = text or args.get("say") or line("go_web" if name == "web_search" else "go_files", spicy)
                query = args["query"]
                if name == "find_files":
                    query = keep_sort_words(asked, query)
                return Decision(name, say, query)
        if FETCH_REQUEST.search(asked):  # small models sometimes just chat instead of fetching
            return RuleBrain().decide(history, spicy)
        return Decision("chat", text or "…")

    def summarize(self, history, query, hits, spicy=False):
        """Turn web results into a short in-character answer that cites sources."""
        results = "\n".join(f"- {h.title} ({h.domain}): {h.snippet}" for h in hits[:5])
        prompt = (f'You searched the web for "{query}". Results:\n{results}\n\n'
                  "Answer the user's question from these results in 2-4 sentences, in character. "
                  "Mention which site(s) it came from. Don't list links; they're already shown.")
        message = self._chat(history[-HISTORY_LIMIT:] + [{"role": "user", "content": prompt}], spicy, tools=False)
        return strip_think(message.get("content", ""))


def keep_sort_words(asked, query):
    """Put back words like "random"/"biggest" and size filters like "over 2gb"
    if the model dropped them from the query."""
    have = set(query.lower().split())
    missing = [w for w in re.findall(r"[a-z]+", asked.lower()) if w in SORT_WORDS and w not in have]
    size = size_phrase(asked)
    if size and not size_phrase(query):
        missing.append(size)
    return " ".join([*dict.fromkeys(missing), query]) if missing else query


def strip_think(text):
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


class HybridBrain(OllamaBrain):
    """For tiny models that chat fine but won't use tools: keyword rules decide
    when to fetch files / search the web, the model does the talking."""

    def decide(self, history, spicy=False):
        ruled = RuleBrain().decide(history, spicy)
        if ruled.action != "chat":
            return ruled
        message = self._chat(history[-HISTORY_LIMIT:], spicy, tools=False)
        return Decision("chat", strip_think(message.get("content", "")) or "…")


# (model, min RAM in GB, brain class), best first. Picked by what this machine can run.
MODEL_LADDER = [
    ("qwen3.5:4b", 16, OllamaBrain),
    ("qwen3.5:2b", 8, OllamaBrain),
    ("qwen3:1.7b", 0, HybridBrain),
]


def total_ram_gb():
    try:
        if sys.platform == "darwin":
            return int(subprocess.check_output(["sysctl", "-n", "hw.memsize"])) / 2**30
        if sys.platform == "win32":
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                            ("total", ctypes.c_ulonglong), ("avail", ctypes.c_ulonglong),
                            ("page_total", ctypes.c_ulonglong), ("page_avail", ctypes.c_ulonglong),
                            ("virt_total", ctypes.c_ulonglong), ("virt_avail", ctypes.c_ulonglong),
                            ("ext", ctypes.c_ulonglong)]
            status = MemoryStatus(length=ctypes.sizeof(MemoryStatus))
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return status.total / 2**30
        with open("/proc/meminfo") as f:
            return int(f.readline().split()[1]) / 2**20
    except (OSError, ValueError, subprocess.SubprocessError):
        return 8.0


def recommended_model(ram_gb=None):
    ram_gb = total_ram_gb() if ram_gb is None else ram_gb
    return next(model for model, need, _cls in MODEL_LADDER if ram_gb >= need)


def pick_brain(override=None):
    """Best installed model this machine can handle, or RuleBrain if none/Ollama is off.
    override: a model name from settings (any installed Ollama model)."""
    installed = installed_models()
    if not installed:
        return RuleBrain()
    if override and override in installed:
        cls = next((c for m, _n, c in MODEL_LADDER if m == override), OllamaBrain)
        return cls(override)
    ram = total_ram_gb()
    for model, need, cls in MODEL_LADDER:
        if ram >= need and model in installed:
            return cls(model)
    return RuleBrain()


# --- running Ollama for the user (no terminal needed) ---------------------------

_server = None  # the `ollama serve` process we started, if any


def find_ollama():
    """Path to the ollama binary, or None if it isn't installed."""
    candidates = [shutil.which("ollama")]
    if sys.platform == "darwin":
        candidates += ["/Applications/Ollama.app/Contents/Resources/ollama",
                       "/opt/homebrew/bin/ollama", "/usr/local/bin/ollama"]
    elif sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        candidates += [os.path.join(local, "Programs", "Ollama", "ollama.exe")]
    else:
        candidates += ["/usr/local/bin/ollama", "/usr/bin/ollama"]
    return next((c for c in candidates if c and os.path.isfile(c)), None)


def ollama_up():
    try:
        ollama("/api/version", timeout=1)
        return True
    except (OSError, ValueError):
        return False


def start_server(wait_s=20):
    """Start `ollama serve` hidden in the background. True once it answers."""
    global _server
    if ollama_up():
        return True
    binary = find_ollama()
    if not binary:
        return False
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    _server = subprocess.Popen([binary, "serve"], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, creationflags=flags)
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        if ollama_up():
            return True
        time.sleep(0.3)
    return False


def stop_server():
    """Stop Ollama only if we were the ones who started it."""
    if _server and _server.poll() is None:
        _server.terminate()


def pull(model, progress):
    """Download a model, calling progress(text) as it goes."""
    request = urllib.request.Request(
        OLLAMA + "/api/pull", data=json.dumps({"model": model, "stream": True}).encode(),
        headers={"Content-Type": "application/json"})
    last = -1
    with urllib.request.urlopen(request, timeout=60) as response:
        for raw in response:
            event = json.loads(raw)
            if event.get("error"):
                raise RuntimeError(event["error"])
            total, done = event.get("total"), event.get("completed")
            if total and done:
                pct = int(done * 100 / total)
                if pct != last:
                    last = pct
                    progress(f"Downloading my brain… {pct}% ({total / 1e9:.1f} GB)")


# --- cloud brains through the user's own CLIs (Claude Code / Codex) ------------------

HOME = os.path.expanduser("~")
# GUI apps get a bare PATH, so look where these CLIs (and node, for Codex) usually live.
EXTRA_PATHS = [os.path.join(HOME, ".local", "bin"), os.path.join(HOME, ".claude", "local"),
               "/opt/homebrew/bin", "/usr/local/bin", os.path.join(HOME, ".npm-global", "bin"),
               os.path.join(os.environ.get("APPDATA", ""), "npm")]
CLI_BRAINS = {"claude": "Claude Code", "codex": "Codex"}
INSTALL_PAGES = {
    "claude": "https://code.claude.com/docs/en/setup",
    "codex": "https://developers.openai.com/codex/cli",
    "local": "https://ollama.com/download",
}
CLI_TIMEOUT_S = 90
SANDBOX = os.path.join(HOME, ".pixel-buddy", "cli-sandbox")  # empty folder: no project files leak in

CLI_PERSONA = PERSONA.split("You can do two things with tools:")[0] + """
Every reply is ONLY a JSON object, nothing else:
{{"action": "chat" | "find_files" | "web_search", "text": "<your short in-character line>", "query": "<search words, or empty>"}}
- find_files: they want a file on their computer (or ask where one is, or "a random ___").
  query = the important words; ALWAYS keep words like random, any, biggest, smallest,
  newest, oldest, size limits like "over 2gb" / "under 10mb", and file types like 3mf, stl, pdf.
- web_search: ONLY when they ask you to look something up / search / google it,
  or say yes after you offered.
- chat: everything else. If it needs current online info, answer briefly if you can
  and offer: "Want me to dig on the web?"
Never make up file names or paths."""


def cli_env():
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([env.get("PATH", ""), *EXTRA_PATHS])
    return env


def find_cli(name):
    """Full path to the `claude` / `codex` CLI, or None if it isn't installed."""
    return shutil.which(name, path=cli_env()["PATH"])


def available_brains():
    """{"claude": path, "codex": path} for the CLIs installed on this machine."""
    return {key: path for key in CLI_BRAINS if (path := find_cli(key))}


def parse_decision(raw, asked, spicy):
    """Pull the JSON decision out of a CLI reply (tolerates ```json fences / extra text)."""
    match = re.search(r"\{.*\}", raw or "", re.S)
    try:
        data = json.loads(match.group(0)) if match else {}
    except ValueError:
        data = {}
    action, text, query = data.get("action"), (data.get("text") or "").strip(), (data.get("query") or "").strip()
    if action in ("find_files", "web_search") and query:
        if action == "find_files":
            query = keep_sort_words(asked, query)
        return Decision(action, text or line("go_web" if action == "web_search" else "go_files", spicy), query)
    if not data and FETCH_REQUEST.search(asked):
        return RuleBrain().decide([{"role": "user", "content": asked}], spicy)
    return Decision("chat", text or strip_think(raw) or "…")


class CLIBrain:
    """Uses the user's own Claude Code or Codex login. Tools are switched off: he only
    ever gets text back, and does all file/web work himself."""

    def __init__(self, kind, path, model=None):
        self.kind, self.path = kind, path
        self.model = model or default_model(kind)
        self.name = f"{CLI_BRAINS[kind]} · {model_label(kind, self.model)}"

    def _run(self, system, prompt):
        os.makedirs(SANDBOX, exist_ok=True)
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        if self.kind == "claude":
            cmd = [self.path, "-p", "--model", self.model, "--tools", "", "--setting-sources", "",
                   "--strict-mcp-config", "--no-session-persistence", "--disable-slash-commands",
                   "--system-prompt", system, "--output-format", "json"]
            stdin = prompt
        else:
            out_file = os.path.join(SANDBOX, "last-reply.txt")
            cmd = [self.path, "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only",
                   "-C", SANDBOX, "--color", "never", "-o", out_file]
            cmd += (["-m", self.model] if self.model else []) + ["-"]
            stdin = system + "\n\n" + prompt
        done = subprocess.run(cmd, input=stdin, capture_output=True, text=True, cwd=SANDBOX,
                              env=cli_env(), timeout=CLI_TIMEOUT_S, creationflags=flags)
        if self.kind == "claude":
            result = json.loads(done.stdout or "{}")
            if result.get("is_error") or "Not logged in" in result.get("result", ""):
                raise RuntimeError(result.get("result") or done.stderr[-300:])
            return result.get("result", "")
        if done.returncode != 0:
            raise RuntimeError(done.stderr[-300:])
        with open(out_file, encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def _transcript(history):
        lines = [f"{'User' if m['role'] == 'user' else 'Crab'}: {m['content']}" for m in history[-12:]]
        return "Conversation so far:\n" + "\n".join(lines)

    def decide(self, history, spicy=False):
        system = CLI_PERSONA.format(voice=VOICES[spicy])
        raw = self._run(system, self._transcript(history) + "\n\nReply to the user's last message as JSON.")
        return parse_decision(raw, history[-1]["content"], spicy)

    def summarize(self, history, query, hits, spicy=False):
        results = "\n".join(f"- {h.title} ({h.domain}): {h.snippet}" for h in hits[:5])
        system = CLI_PERSONA.split("Every reply is ONLY")[0].format(voice=VOICES[spicy])
        prompt = (self._transcript(history) + f'\n\nYou searched the web for "{query}". Results:\n{results}\n\n'
                  "Answer the user from these results in 2-4 sentences, in character, plain text "
                  "(no JSON, no links). Mention which site(s) it came from.")
        return strip_think(self._run(system, prompt))


# --- models you can pick, and how smart each one is --------------------------------
# "smarts" is a rough 0-10 score, only used so he can react to upgrades/downgrades.

CLAUDE_MODELS = [  # (model ID, label, smarts), weakest first
    ("claude-haiku-4-5", "Haiku 4.5", 4),
    ("claude-sonnet-5", "Sonnet 5", 6),
    ("claude-opus-5-5", "Opus 5.5", 8),
    ("claude-fable-5-1", "Fable 5.1 (needs usage credits)", 9.5),
]
CODEX_MODELS_CACHE = os.path.join(HOME, ".codex", "models_cache.json")


def codex_models():
    """Models this Codex install offers (its own cache), weakest first."""
    try:
        with open(CODEX_MODELS_CACHE, encoding="utf-8") as f:
            listed = [m for m in json.load(f)["models"] if m.get("visibility") == "list"]
    except (OSError, ValueError, KeyError, TypeError):
        return []
    listed.sort(key=lambda m: m.get("priority", 99))  # Codex lists its best model first
    best = len(listed)
    return [(m["slug"], m.get("display_name", m["slug"]), 4.5 + 4.5 * (best - i) / best)
            for i, m in enumerate(listed)][::-1]


def local_models():
    """Installed Ollama models, smallest (dumbest) first. Works even when Ollama is off."""
    root = os.path.join(HOME, ".ollama", "models", "manifests", "registry.ollama.ai", "library")
    found = []
    for name in (os.listdir(root) if os.path.isdir(root) else []):
        for tag in os.listdir(os.path.join(root, name)):
            try:
                with open(os.path.join(root, name, tag), encoding="utf-8") as f:
                    size = sum(layer["size"] for layer in json.load(f)["layers"])
            except (OSError, ValueError, KeyError):
                continue
            found.append((f"{name}:{tag}", size))
    found.sort(key=lambda item: item[1])
    # Local models top out around "decent": 1 (tiny) .. 3.5 (biggest you have).
    return [(model, f"{model} ({size / 1e9:.1f} GB)", 1 + 2.5 * i / max(1, len(found) - 1))
            for i, (model, size) in enumerate(found)]


def model_options(kind):
    return {"claude": CLAUDE_MODELS, "codex": codex_models(), "local": local_models()}.get(kind, [])


def default_model(kind):
    if kind == "claude":
        return "claude-haiku-4-5"  # fast and cheap: plenty for a desktop crab
    if kind == "codex":
        options = codex_models()
        return options[-1][0] if options else None  # Codex's own top pick
    return None


def model_label(kind, model):
    for key, label, _smarts in model_options(kind):
        if key == model:
            return label.split(" (")[0]
    return model or "default"


def smarts(kind, model):
    """How smart a brain+model is (0 = keywords only)."""
    if kind == "keywords":
        return 0
    if kind == "local" and not model:
        model = recommended_model()
    options = model_options(kind)
    for key, _label, score in options:
        if key == model:
            return score
    return options[-1][2] if options else 1


def setup_brain(choice="local", models=None, progress=lambda text: None):
    """Everything needed for a working brain, done in the background.
    choice: "local" (Ollama), "claude", "codex", or "keywords".
    models: {"local": ..., "claude": ..., "codex": ...} picked in his menu."""
    models = models or {}
    if choice == "keywords":
        return RuleBrain()
    if choice in CLI_BRAINS:
        path = find_cli(choice)
        if path:
            return CLIBrain(choice, path, models.get(choice))
        print(f"{choice} CLI not found; using the local brain", file=sys.stderr)
    return setup_local_brain(models.get("local"), progress)


def setup_local_brain(override=None, progress=lambda text: None):
    """Start Ollama, download the right model if it's missing, pick it."""
    progress("Waking up my brain…")
    if not start_server():
        progress("")
        return RuleBrain()
    model = override or recommended_model()
    if model not in installed_models():
        try:
            pull(model, progress)
        except (OSError, ValueError, RuntimeError) as err:
            print(f"couldn't download {model}: {err}", file=sys.stderr)
    progress("")
    return pick_brain(override)
