"""Pixel Buddy: a desktop crab that wanders your screen and fetches files.

Click him, type what you're looking for, and he runs off to find it, then drags
it back. The bigger the file, the harder he struggles.
Run:  python buddy.py
"""

import json
from html import escape
import math
import os
import random
import re
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction, QColor, QDesktopServices, QFont, QFontMetrics, QIcon, QPainter, QPainterPath, QPen, QPixmap,
    QRegion, QTransform,
)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

import hardware
import update
import web
from brain import (
    CLI_BRAINS, FETCH_REQUEST, INSTALL_PAGES, WEB_HINTS, RuleBrain, available_brains, find_ollama,
    install_and_pull, model_label, model_options, setup_brain, smarts, stop_server,
)
from desktop import show_everywhere
from lines import clean_language, line
from preview import make_preview
from search import FileIndex
from voice import Voice
from ui import MONO, HistoryBox, InputBox, ModelCard, ResultCard, WebCard

ASSETS = Path(__file__).parent / "assets"
SCALE = 4                   # 32px sprites -> 128px on screen
SPRITE_PX = 32                # sprite art is 32x32 pixels
SPRITE = SPRITE_PX * SCALE
WIN_W, WIN_H = 420, 300     # room around the crab for bubbles and the carried file
TICK_MS = 33                # ~30 fps movement
FRAME_MS = {"walk": 140, "idle": 500, "sleep": 900, "happy": 250, "confused": 400, "pull": 170,
            "game_modern": 160, "game_retro": 220, "inspect": 320, "install": 240}
GAMING = ("game_modern", "game_retro")
GAME_CHANCE = 0.15          # chance an idle break turns into a gaming session
GAME_SECONDS = (20, 45)
GAME_STYLES = {"both": GAMING, "retro": ("game_retro",), "modern": ("game_modern",), "off": ()}
# Where the controller cord runs, in sprite pixels (drawn facing right): pad -> console.
CORD_FROM, CORD_TO = (30, 21), (25, 21)
WALK_SPEED = 1.6            # px per tick while wandering
RUN_SPEED = 6.0             # searching / running off screen
GRAVITY = 1.2
SLEEP_AFTER_S = 60          # nap after this long without being clicked
MIN_SEARCH_S = 2.5          # always put on a bit of a show
OFFSCREEN_S = 1.2           # how long he's "gone" fetching the file
PREVIEW_WAIT_S = 5          # max extra time offscreen waiting for a preview image
MIN_INSPECT_S = 7           # the hardware check is quick; the show shouldn't be
ROPE_CLAW = (13, 70)        # gripping claw centre, from the sprite's rope-side edge
HOLD_Y = 50                 # light files: bottom edge sits in his raised claws

ROPE = QColor(201, 154, 91)
ROPE_DARK = QColor(92, 58, 30)
ROPE_STRAND = QColor(140, 98, 53)

TASK_MODES = {"searching", "found", "exiting", "offscreen", "returning", "presenting",
              "inspecting", "installing", "updating"}

# "install ollama" / "get a brain", typed into the chat box.
BRAIN_REQUEST = re.compile(
    r"\b(install|get|download|set ?up|find)\b.{0,20}\b(ollama|a brain|your brain|local ai|local model)\b"
    r"|\b(check|scan|look at)\b.{0,20}\b(my )?(specs|hardware|rig|pc|computer|machine)\b",
    re.I,
)

# Typed voice switches, handled before the brain sees the message.
MUTE_REQUEST = re.compile(r"^\W*(shut ?up|be quiet|mute|stop talking|quiet|hush|silence|shh+)\b", re.I)
UNMUTE_REQUEST = re.compile(r"^\W*(unmute|talk to me|speak up|talk out loud|use your voice)\b", re.I)

INK = QColor(58, 16, 20)
BUBBLE_FONT = QFont(MONO, 12, QFont.Bold)
LABEL_FONT = QFont(MONO, 9, QFont.Bold)
BADGE_FONT = QFont(MONO, 11, QFont.Bold)


@dataclass(frozen=True)
class Tier:
    """How hard a file is to drag, picked by its size."""
    max_bytes: float
    cargo_px: int       # how big the file looks
    speed: float        # px per tick at full effort
    tug: float          # 0 = smooth, 1 = jerky tug-tug-tug
    rest_every: float   # px between breathers (0 = never)
    rest_s: float
    wobble: float       # degrees the file rocks
    max_walk: int       # how far he'll drag it on screen
    sprite: str         # "walk" = carried overhead, "pull" = roped and dragged
    level: int          # picks his lines: tier{level}_start / _grunt / _pant
    dust: bool = False


TIERS = [
    Tier(5e6, 100, 3.0, 0.0, 0, 0, 3, 10_000, "walk", 0),
    Tier(100e6, 88, 2.2, 0.35, 0, 0, 5, 600, "pull", 1),
    Tier(1e9, 100, 1.6, 0.55, 150, 1.0, 6, 420, "pull", 2, True),
    Tier(float("inf"), 112, 1.3, 0.7, 90, 1.6, 8, 230, "pull", 3, True),
]


SETTINGS_FILE = Path.home() / ".pixel-buddy.json"


def load_settings():
    try:
        settings = {"potty_mouth": True, **json.loads(SETTINGS_FILE.read_text())}
    except (OSError, ValueError):
        return {"potty_mouth": True}
    if "model" in settings:  # older versions: one local-model override
        settings.setdefault("models", {})["local"] = settings.pop("model")
    return settings


def save_settings(settings):
    try:
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2))
    except OSError as err:
        print(f"couldn't save settings: {err}", file=sys.stderr)


def tier_for(size):
    return next(t for t in TIERS if size < t.max_bytes)


BUBBLE_MAX_H = 170          # tallest speech bubble that still fits above him
BUBBLE_MORE = "… (full answer in Chat history)"


def bubble_text_height(text):
    fm = QFontMetrics(BUBBLE_FONT)
    return fm.boundingRect(QRect(0, 0, WIN_W - 32, 1000), Qt.TextWordWrap | Qt.AlignCenter, text).height()


def fit_bubble(text):
    """Trim long answers word by word until the bubble fits above him."""
    if bubble_text_height(text) <= BUBBLE_MAX_H:
        return text
    words = text.split(" ")
    while words and bubble_text_height(" ".join(words) + BUBBLE_MORE) > BUBBLE_MAX_H:
        words.pop()
    return " ".join(words) + BUBBLE_MORE


def breakable_path(path):
    """Let long paths wrap at each folder separator (zero-width space after it)."""
    return str(path).replace(os.sep, os.sep + "​")


def load_pixmap(path, scale):
    pix = QPixmap(str(path))
    return pix.scaled(pix.width() * scale, pix.height() * scale, Qt.KeepAspectRatio, Qt.FastTransformation)


def load_frames():
    frames = {}
    for name in FRAME_MS:
        paths = sorted(ASSETS.glob(f"{name}_*.png"))
        if not paths:
            sys.exit(f"Missing sprites in {ASSETS}. Run: python make_sprites.py")
        frames[name] = [load_pixmap(p, SCALE) for p in paths]
    # Pull frames have the rope on his left and gaming frames face right; the "_r"
    # copies are mirrored for the other side.
    for name in ("pull", *GAMING):
        frames[name + "_r"] = mirrored(frames[name])
    return frames


def mirrored(pixmaps):
    return [pix.transformed(QTransform().scale(-1, 1)) for pix in pixmaps]


def previews_job(hits, out):
    """Worker thread: fill `out` with {path: QImage}, best match first."""
    for hit in hits:
        out[hit.path] = make_preview(hit.path)
    return out


class Buddy(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)  # stay visible when app isn't focused
        self.setFixedSize(WIN_W, WIN_H)

        self.frames = load_frames()
        self.file_icon = QPixmap(str(ASSETS / "file.png"))

        # Animation
        self.state = "idle"
        self.frame = 0
        self.last_frame_at = 0.0
        self.state_until = time.monotonic() + 2
        self.speed = WALK_SPEED
        self.bubble = None
        self.bubble_until = 0.0
        self._mask_key = None

        # Behaviour: roam | chatting | thinking | searching | found | exiting | offscreen | returning | presenting
        self.mode = "roam"
        self.last_poke = time.monotonic()
        self.target_x = 0.0
        self.home_x = 0.0
        self.mode_until = 0.0

        # Dragging a file back
        self.carrying = None        # what he's hauling (a file Hit, or web results)
        self.carry_tag = ""         # "name · size" label on it
        self.cargo = None           # QPixmap of it (preview or big file icon)
        self.tier = TIERS[0]
        self.carry_on_right = False
        self.exit_left = False
        self.task_floor = None      # screen rect he's pinned to during a fetch
        self.walked_since_rest = 0.0
        self.resting_until = 0.0
        self.next_grunt_at = 0.0
        self.wobble = 0.0
        self.effort = 1.0           # 0 = resting (rope slack), 1 = pulling hard

        # Physics / mouse
        self.fall_speed = 0.0
        self.falling = False
        self.drag_offset = None
        self.drag_moved = False

        # Search + previews run on a worker thread so the animation never freezes.
        self.index = FileIndex()
        self.worker = ThreadPoolExecutor(max_workers=1)
        self.worker.submit(self.index.build)
        self.query = ""
        self.search_job = None
        self.preview_job = None
        self.preview_images = {}    # filled by the worker (QImage)
        self.previews = {}          # converted on the UI thread (QPixmap)
        self.card_preview_count = 0
        self.hits = []
        self.web_mode = False       # current search is a web search
        self.net = ThreadPoolExecutor(max_workers=1)  # web requests never wait on the file index
        self.thinker = ThreadPoolExecutor(max_workers=1)  # the brain never blocks searches
        self.brain = RuleBrain()
        self.history = []           # chat so far: [{"role": "user"|"assistant", "content": str}]
        self.think_job = None
        self.summary_job = None     # brain reading web results
        self.settings = load_settings()
        self.voice = Voice(self.settings)
        self.brain_progress = ""    # set by the setup thread ("Downloading my brain… 42%")
        self.brain_job = None
        self.load_brain()
        self.globe = QPixmap(str(ASSETS / "globe.png"))
        self.tvs = {}               # "game_retro" -> [frames facing right], "+_r" mirrored
        for state in GAMING:
            style = state.removeprefix("game_")
            self.tvs[state] = [load_pixmap(ASSETS / f"tv_{style}_{i}.png", SCALE) for i in range(4)]
            self.tvs[state + "_r"] = mirrored(self.tvs[state])
        self.game_faces_left = False
        self.next_game_line = 0.0

        self.input = InputBox()     # click him → type here; he answers in his bubble
        self.input.sent.connect(self.on_message)
        self.chat = HistoryBox()    # right-click → Chat history
        self.chat.set_status("brain: waking up…")
        self.card = ResultCard()
        self.web_card = WebCard()
        self.model_card = ModelCard()   # hardware check → the brains this machine can run
        self.model_card.chosen.connect(self.install_brain)
        self.specs = None
        self.specs_job = None
        self.install_job = None
        self.update_job = None
        self.next_show_line = 0.0       # paces his chatter while inspecting / downloading

        floor = self.floor_rect()
        self.x_pos = float(floor.center().x() - WIN_W // 2)
        self.y_pos = float(self.floor_y())
        self.move(int(self.x_pos), int(self.y_pos))

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(TICK_MS)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, lambda: show_everywhere(self))  # also over full-screen apps

    # --- geometry ------------------------------------------------------------

    def floor_rect(self):
        # During a fetch he sticks to the screen he started on; otherwise running
        # "off screen" would land him on the next monitor and flip his directions.
        if self.mode in TASK_MODES and self.task_floor is not None:
            return self.task_floor
        screen = self.screen() or QApplication.primaryScreen()
        return screen.availableGeometry()  # excludes the Dock / taskbar

    def floor_y(self):
        return self.floor_rect().bottom() - WIN_H + 1

    def clamp_x(self, x):
        floor = self.floor_rect()
        return max(floor.left(), min(x, floor.right() - WIN_W))

    def sprite_rect(self):
        return QRect((WIN_W - SPRITE) // 2, WIN_H - SPRITE, SPRITE, SPRITE)

    @property
    def held(self):
        """Light files are carried overhead; everything else gets roped and dragged."""
        return self.tier.sprite == "walk"

    def carry_rects(self):
        """(cargo rect, name label rect): overhead in his claws, or trailing behind him."""
        size = self.tier.cargo_px
        sprite = self.sprite_rect()
        if self.held:
            bounce = 3 if self.state == "walk" and self.frame % 2 else 0
            cargo = QRect(sprite.center().x() - size // 2 + 1, sprite.top() + HOLD_Y - size + bounce, size, size)
        else:
            x = sprite.right() + 14 if self.carry_on_right else sprite.left() - size - 14
            cargo = QRect(x, WIN_H - size - 2, size, size)
        label = QRect(cargo.center().x() - 60, cargo.top() - 24, 120, 18)
        return cargo, label

    def rope_claw(self):
        sprite = self.sprite_rect()
        dx, dy = ROPE_CLAW
        x = sprite.right() - dx if self.carry_on_right else sprite.left() + dx
        return QPointF(x, sprite.top() + dy + (4 if self.frame % 2 else 0))

    def bubble_rect(self):
        if not self.bubble:
            return QRect()
        fm = QFontMetrics(BUBBLE_FONT)
        text = fm.boundingRect(QRect(0, 0, WIN_W - 32, 400), Qt.TextWordWrap | Qt.AlignCenter, self.bubble)
        w, h = text.width() + 24, text.height() + 14
        bottom = WIN_H - SPRITE + 20  # just above his eyes
        if self.carrying:  # stay above the file's name tag
            bottom = min(bottom, self.carry_rects()[1].top() - 4)
        if self.state == "sleep":  # float the Zzz up and off to the side of his nightcap
            return QRect(self.sprite_rect().right() - 8, bottom - h - 16, w, h)
        return QRect((WIN_W - w) // 2, bottom - h, w, h)

    # --- small helpers -------------------------------------------------------

    def set_state(self, state, duration=None):
        if state != self.state:
            self.state = state
            self.frame = 0
        self.state_until = time.monotonic() + duration if duration else float("inf")

    def speak(self, key, seconds=3, **fmt):
        """Say one of his lines (lines.py), clean or potty-mouthed per settings."""
        self.say(line(key, self.settings["potty_mouth"], **fmt), seconds)

    def say(self, text, seconds=3):
        text = clean_language(text)
        self.bubble = fit_bubble(text)
        self.bubble_until = time.monotonic() + seconds
        self.voice.say(text)  # full text, even if the bubble had to be trimmed

    def walk_toward(self, target, speed, sprite="walk"):
        """Step toward target x. Returns True on arrival."""
        self.set_state(sprite)
        self.speed = max(speed, 0.3)
        if abs(target - self.x_pos) <= speed:
            self.x_pos = target
            return True
        self.x_pos += speed if target > self.x_pos else -speed
        return False

    def current_pixmap(self):
        flip = (self.state == "pull" and self.carry_on_right) or (self.state in GAMING and self.game_faces_left)
        return self.frames[self.state + "_r" if flip else self.state][self.frame]

    # --- behaviour: one handler per mode --------------------------------------

    def tick(self):
        now = time.monotonic()

        if self.drag_offset is None:
            if self.falling:
                self.fall_speed += GRAVITY
                self.y_pos = min(self.y_pos + self.fall_speed, self.floor_y())
                if self.y_pos >= self.floor_y():
                    self.falling = False
                    self.speak("dropped", 1.5)
                    self.set_state("idle", 1.5)
            else:
                getattr(self, f"do_{self.mode}")(now)
            self.move(int(self.x_pos), int(self.y_pos))

        moving = self.state in ("walk", "pull")
        frame_ms = FRAME_MS[self.state] * (WALK_SPEED / self.speed if moving else 1)
        if now - self.last_frame_at >= min(frame_ms, 900) / 1000:
            self.frame = (self.frame + 1) % len(self.frames[self.state])
            self.last_frame_at = now

        if self.state == "sleep":
            self.bubble, self.bubble_until = "Z" + "z" * (1 + self.frame), now + 1
        elif self.bubble and now > self.bubble_until:
            self.bubble = None

        self.poll_brain()
        self.update_mask()
        self.update()

    def load_brain(self):
        """(Re)build his brain in the background from settings: local, claude, codex, keywords."""
        self.brain_job = self.thinker.submit(
            setup_brain, self.settings.get("brain", "local"), self.models(), self._brain_progress)

    def models(self):
        """{"local": model, "claude": model, "codex": model} picked in his menu."""
        return self.settings.setdefault("models", {})

    def set_brain(self, choice, model=None):
        """Switch brain (and model), and have him react to the upgrade or downgrade."""
        was = self.settings.get("brain", "local")
        before = smarts(was, self.models().get(was))
        self.settings["brain"] = choice
        if model:
            self.models()[choice] = model
        save_settings(self.settings)
        if choice != "local":
            stop_server()  # free the local model's RAM if he started it
        self.brain = RuleBrain()  # keyword mode until the new brain is ready
        self.chat.set_status("brain: waking up…")
        self.load_brain()

        after = smarts(choice, self.models().get(choice))
        # Upgrade/downgrade calls are only made where the ranking is real: models from the
        # same maker, or local vs cloud. Claude <-> Codex is just "switching teams".
        tier = {"keywords": 0, "local": 1, "claude": 2, "codex": 2}
        if choice == "keywords":
            key = "brain_off"
        elif choice != was and tier[choice] == tier[was]:
            key = "brain_swap"
        else:
            rise = after - before if choice == was else tier[choice] - tier[was]
            key = "brain_up" if rise > 0.5 else "brain_down" if rise < -0.5 else "brain_same"
        self.set_state({"brain_up": "happy", "brain_down": "confused", "brain_off": "confused"}.get(key, "idle"), 3)
        self.speak(key, 5, name=self.brain_title(choice))

    def brain_title(self, choice):
        """What he calls his brain, e.g. "Claude Opus 5.5", "Codex GPT-6-Astra", "qwen3.5:4b"."""
        model = self.models().get(choice)
        if choice == "claude":
            return "Claude " + model_label("claude", model or "claude-haiku-4-5")
        if choice == "codex":
            return "Codex " + model_label("codex", model) if model else "Codex"
        return model or "my local brain"

    def _brain_progress(self, text):
        self.brain_progress = text  # called from the setup thread; read by poll_brain

    def poll_brain(self):
        """Pick up background brain work: setup progress, model choice, web summaries."""
        if self.brain_job and not self.brain_job.done() and self.brain_progress:
            self.chat.set_status(self.brain_progress)
            if self.mode in ("roam", "chatting") and self.state != "sleep":
                self.bubble, self.bubble_until = self.brain_progress, time.monotonic() + 1
        if self.brain_job and self.brain_job.done():
            try:
                self.brain = self.brain_job.result()
            except Exception as err:  # noqa: BLE001
                print(f"no local AI: {err}", file=sys.stderr)
            self.brain_job = None
            label = "no AI (keyword mode)" if isinstance(self.brain, RuleBrain) else self.brain.name
            self.chat.set_status(f"brain: {label}")
            self.maybe_suggest_upgrade()
        if self.summary_job and self.summary_job.done():
            try:
                self.reply(self.summary_job.result())
            except Exception as err:  # noqa: BLE001 - links are already in the chat
                print(f"summary failed: {err}", file=sys.stderr)
                self.chat.set_typing(False)
            self.summary_job = None

    def do_roam(self, now):
        if self.state == "walk":
            if self.walk_toward(self.target_x, WALK_SPEED):
                self.pick_next_action()
        elif now >= self.state_until:
            self.pick_next_action()
        elif self.state in GAMING and now >= self.next_game_line and now > self.bubble_until:
            self.speak("gaming", 2.5)  # trash talk
            self.next_game_line = now + random.uniform(6, 12)

    def pick_next_action(self):
        if time.monotonic() - self.last_poke > SLEEP_AFTER_S:
            self.set_state("sleep")
        elif random.random() < GAME_CHANCE and self.game_choices():
            self.start_gaming()
        elif random.random() < 0.6:
            floor = self.floor_rect()
            self.target_x = random.randint(floor.left(), floor.right() - WIN_W)
            self.set_state("walk")
        else:
            self.set_state("idle", random.uniform(2, 5))

    def do_chatting(self, _now):
        if not self.input.isVisible():
            self.mode = "roam"
            self.set_state("idle", 1)

    def do_thinking(self, now):
        self.set_state("idle")
        self.say("." * (1 + int(now * 3) % 3), 1)
        if not self.think_job.done():
            return
        try:
            decision = self.think_job.result()
        except Exception as err:  # noqa: BLE001 - a broken brain falls back to rules
            print(f"brain failed, using rules: {err}", file=sys.stderr)
            if not isinstance(err, OSError):  # e.g. "Fable 5.1 requires usage credits"
                reason = str(err).strip().splitlines()[0][:90] if str(err).strip() else type(err).__name__
                self.reply(line("brain_error", self.settings["potty_mouth"], err=reason))
            decision = RuleBrain().decide(self.history, self.settings["potty_mouth"])
            if decision.action == "chat":  # nothing to fetch: the error line says it all
                self.mode = "chatting"
                self.set_state("confused", 2)
                return
        self.reply(decision.text)
        if decision.action in ("find_files", "web_search") and decision.query:
            self.start_search(decision.query, decision.action == "web_search")
        else:
            self.mode = "chatting"
            self.set_state("happy", 1.5)

    def reply(self, text, bubble=True):
        """Add his message to the chat (and his speech bubble)."""
        if not text:
            return
        text = clean_language(text)
        self.history.append({"role": "assistant", "content": text})
        self.chat.add("crab", escape(text).replace("\n", "<br>"))
        if bubble:
            self.say(text, min(20, max(4, len(text) / 14)))  # longer answers stay up longer

    def after_task(self):
        self.mode = "chatting" if self.input.isVisible() else "roam"
        self.set_state("idle", 2)

    def do_searching(self, now):
        if self.walk_toward(self.target_x, RUN_SPEED):
            # Pace back and forth around where he started.
            left, right = self.clamp_x(self.home_x - 160), self.clamp_x(self.home_x + 160)
            self.target_x = right if self.x_pos <= left else left
        if now < self.mode_until or not self.search_job.done():
            return
        try:
            self.hits = self.search_job.result()
        except Exception as err:  # noqa: BLE001 - surface anything to the user
            self.hits = []
            print(f"search failed: {err}", file=sys.stderr)
            if self.web_mode:  # offline / DuckDuckGo changed: fall back to the browser
                QDesktopServices.openUrl(QUrl(web.browser_url(self.query)))
                self.after_task()
                self.set_state("confused", 4)
                self.reply(line("web_failed", self.settings["potty_mouth"]))
                return
        if self.hits:
            if not self.web_mode:
                self.preview_images = {}
                self.preview_job = self.worker.submit(previews_job, self.hits, self.preview_images)
            self.mode = "found"
            self.set_state("happy", 1.5)
            self.speak("found", 2)
        else:
            self.after_task()
            self.set_state("confused", 4)
            self.reply(line("not_found", self.settings["potty_mouth"], q=self.query))

    def do_found(self, now):
        if now < self.state_until:
            return
        floor = self.floor_rect()
        self.exit_left = self.x_pos + WIN_W / 2 < floor.center().x()
        self.target_x = floor.left() - WIN_W - 20 if self.exit_left else floor.right() + 20
        self.mode = "exiting"

    def do_exiting(self, now):
        if self.walk_toward(self.target_x, RUN_SPEED):
            self.mode = "offscreen"
            self.mode_until = now + OFFSCREEN_S
            self.set_state("idle")

    def do_offscreen(self, now):
        hit = self.hits[0]
        preview_ready = self.web_mode or hit.path in self.preview_images or self.preview_job.done()
        if now < self.mode_until or (not preview_ready and now < self.mode_until + PREVIEW_WAIT_S):
            return
        self.carrying = hit
        if self.web_mode:  # web results are light: a globe, carried overhead
            self.tier = TIERS[0]
            self.carry_tag = f"{len(self.hits)} web results"
            self.cargo = self.make_cargo(self.globe, "WEB", pixel_art=True)
        else:
            self.tier = tier_for(hit.size)
            self.carry_tag = f"{hit.path.name} · {hit.size_text}"
            self.refresh_previews()
            self.cargo = self.make_cargo(self.previews.get(hit.path), hit.path.suffix.lstrip(".").upper()[:5])

        # Heavy files don't get dragged all the way across the screen.
        floor = self.floor_rect()
        from_left = self.exit_left  # come back the way he left
        sprite = self.sprite_rect()
        if from_left:  # start with the crab just past the edge, file further out
            self.x_pos = float(floor.left() - sprite.right() - 4)
            self.target_x = min(self.home_x, floor.left() + self.tier.max_walk)
        else:
            self.x_pos = float(floor.right() - sprite.left() + 4)
            self.target_x = max(self.home_x, floor.right() - WIN_W - self.tier.max_walk)
        self.carry_on_right = not from_left  # the file trails behind him
        self.walked_since_rest = 0.0
        self.resting_until = 0.0
        self.next_grunt_at = now + random.uniform(1.5, 3)
        self.speak(f"tier{self.tier.level}_start", 2.5, size=getattr(hit, "size_text", ""))
        self.mode = "returning"

    def do_returning(self, now):
        tier = self.tier
        if now < self.resting_until:  # catching his breath
            self.set_state(tier.sprite)
            self.speed = 0.3
            self.wobble *= 0.8
            self.effort = 0.0
            return

        if tier.rest_every and self.walked_since_rest >= tier.rest_every:
            self.walked_since_rest = 0.0
            self.resting_until = now + tier.rest_s
            self.speak(f"tier{tier.level}_pant", tier.rest_s)
            return

        if tier.level > 0 and now >= self.next_grunt_at and now > self.bubble_until:
            self.speak(f"tier{tier.level}_grunt", 1.4)
            self.next_grunt_at = now + random.uniform(2, 4)

        # Tug-tug-tug: effort pulses instead of a smooth glide.
        effort = 1 - tier.tug + tier.tug * abs(math.sin(now * 6))
        before = self.x_pos
        arrived = self.walk_toward(self.target_x, tier.speed * effort, tier.sprite)
        self.walked_since_rest += abs(self.x_pos - before)
        self.wobble = math.sin(now * 9) * tier.wobble * effort
        self.effort = effort
        if arrived:
            self.drop_off()

    def drop_off(self):
        hit = self.carrying
        self.carrying = None
        self.cargo = None
        self.mode = "presenting"
        self.set_state("happy", 2)
        spicy = self.settings["potty_mouth"]
        if self.web_mode:
            self.speak("web_delivered", 6, q=self.query)
            links = "".join(f'<br>• <a href="{escape(h.url)}">{escape(h.title)}</a>' for h in self.hits[:5])
            self.chat.add("crab", escape(line("web_result", spicy, q=self.query)) + links)
            self.history.append({"role": "assistant", "content": "Web results: " + "; ".join(
                f"{h.title} ({h.url})" for h in self.hits[:5])})
            self.web_card.show_hits(self.query, self.hits, self.geometry())
            if hasattr(self.brain, "summarize"):  # let the AI read the results and answer
                self.chat.set_typing(True)
                self.summary_job = self.thinker.submit(
                    self.brain.summarize, list(self.history), self.query, self.hits, spicy)
            return
        self.speak("delivered", 12, path=breakable_path(hit.path.parent))
        folder = str(hit.path.parent)
        self.chat.add("crab", line(
            "file_result", spicy, name=escape(hit.path.name), size=hit.size_text,
            folder=escape(folder), folder_url=QUrl.fromLocalFile(folder).toString(),
        ))
        self.history.append({"role": "assistant", "content": f"Found file: {hit.path}"})
        self.refresh_previews()
        self.card.show_hits(self.hits, self.previews, self.geometry())
        self.card_preview_count = len(self.previews)

    def do_presenting(self, now):
        if self.web_mode:
            if not self.web_card.isVisible():
                self.after_task()
            elif now >= self.state_until:
                self.set_state("idle")
            return
        if not self.card.isVisible():
            self.after_task()
            return
        if now >= self.state_until:
            self.set_state("idle")
        # Late previews (slow Quick Look) show up on the card when ready.
        self.refresh_previews()
        if len(self.previews) > self.card_preview_count:
            self.card_preview_count = len(self.previews)
            self.card.show_hits(self.hits, self.previews, self.geometry())

    # --- checking the machine, then installing a brain -------------------------

    def start_hardware_check(self):
        """Out comes the magnifying glass: he reads the machine, then lists the
        local brains it can actually run."""
        if self.mode in TASK_MODES or self.mode == "thinking":
            self.speak("busy", 1.5)
            return
        self.input.close_card()
        self.card.hide()
        self.web_card.hide()
        self.model_card.hide()
        self.mode = "inspecting"
        self.set_state("inspect")
        self.speak("inspect_start", 3)
        self.mode_until = time.monotonic() + MIN_INSPECT_S
        self.next_show_line = time.monotonic() + 3
        self.specs_job = self.net.submit(hardware.scan)  # the file index keeps the worker busy

    def do_inspecting(self, now):
        self.set_state("inspect")
        if now >= self.next_show_line and now > self.bubble_until:
            self.speak("inspecting", 2.5)
            self.next_show_line = now + random.uniform(2.5, 3.5)
        if now < self.mode_until or not self.specs_job.done():
            return
        try:
            self.specs = self.specs_job.result()
        except Exception as err:  # noqa: BLE001 - never leave him stuck mid-inspection
            print(f"hardware scan failed: {err}", file=sys.stderr)
            self.after_task()
            self.set_state("confused", 3)
            return
        self.specs_job = None
        self.reply(line("inspect_done", self.settings["potty_mouth"], specs=self.specs.summary()))
        self.model_card.show_picks(self.specs, hardware.rank(self.specs), self.geometry())
        self.after_task()
        self.set_state("happy", 2)
        QTimer.singleShot(1200, lambda: self.speak("picks_ready", 5))

    def install_brain(self, model):
        """Go get Ollama (if it's missing) and download `model`."""
        self.mode = "installing"
        self.set_state("install")
        self.speak("install_start", 3)
        self.brain_progress = ""
        self.next_show_line = time.monotonic() + 3
        self.install_job = self.net.submit(install_and_pull, model, self._brain_progress)

    def do_installing(self, now):
        self.set_state("install")
        # Ollama's own download reports percentages; winget doesn't, so he fills the
        # quiet stretches with lines instead of a dead bubble.
        if self.brain_progress:
            self.bubble, self.bubble_until = self.brain_progress, now + 1
        elif now >= self.next_show_line and now > self.bubble_until:
            self.speak("installing", 2.5)
            self.next_show_line = now + random.uniform(3, 5)
        if not self.install_job.done():
            return
        try:
            model = self.install_job.result()
        except Exception as err:  # noqa: BLE001 - surface whatever went wrong and hand off the page
            reason = str(err).strip().splitlines()[0][:90] if str(err).strip() else type(err).__name__
            print(f"brain install failed: {err}", file=sys.stderr)
            self.install_job = None
            self.brain_progress = ""
            self.after_task()
            self.set_state("confused", 4)
            self.reply(line("install_failed", self.settings["potty_mouth"], err=reason))
            QDesktopServices.openUrl(QUrl(INSTALL_PAGES["local"]))
            return
        self.install_job = None
        self.brain_progress = ""
        self.models()["local"] = model
        self.settings["brain"] = "local"
        save_settings(self.settings)
        self.after_task()
        self.set_state("happy", 3)
        self.reply(line("install_done", self.settings["potty_mouth"], model=model))
        self.chat.set_status("brain: waking up…")
        self.load_brain()

    # --- updating himself ------------------------------------------------------

    def check_for_updates(self):
        """Ask GitHub for a newer build. He reuses the download animation: same job,
        he's just fetching himself this time."""
        if not update.frozen():  # from source there's nothing to swap out
            self.speak("update_source", 6)
            QDesktopServices.openUrl(QUrl(update.RELEASES_PAGE))
            return
        if self.mode in TASK_MODES or self.mode == "thinking":
            self.speak("busy", 1.5)
            return
        self.input.close_card()
        self.model_card.hide()
        self.mode = "updating"
        self.set_state("install")
        self.speak("update_checking", 3)
        self.brain_progress = ""
        self.next_show_line = time.monotonic() + 3
        self.update_job = self.net.submit(update.check_and_stage, self._brain_progress)

    def do_updating(self, now):
        self.set_state("install")
        if self.brain_progress:
            self.bubble, self.bubble_until = self.brain_progress, now + 1
        elif now >= self.next_show_line and now > self.bubble_until:
            self.speak("installing", 2.5)  # same "reeling it in" chatter
            self.next_show_line = now + random.uniform(3, 5)
        if not self.update_job.done():
            return
        try:
            found = self.update_job.result()
        except Exception as err:  # noqa: BLE001 - offline, private repo, no build for this OS
            reason = str(err).strip().splitlines()[0][:90] if str(err).strip() else type(err).__name__
            print(f"update check failed: {err}", file=sys.stderr)
            self.update_job = None
            self.brain_progress = ""
            self.after_task()
            self.set_state("confused", 4)
            self.reply(line("update_failed", self.settings["potty_mouth"], err=reason))
            return
        self.update_job = None
        self.brain_progress = ""
        if not found:
            self.after_task()
            self.speak("update_none", 4, version=update.VERSION)
            return
        tag, new_build = found
        self.speak("update_ready", 4, tag=tag)
        update.apply_update(new_build)  # the swap script waits for this process to exit
        QTimer.singleShot(1500, QApplication.quit)

    # --- actions -------------------------------------------------------------

    def refresh_previews(self):
        for path, image in list(self.preview_images.items()):
            if image is not None and path not in self.previews:
                self.previews[path] = QPixmap.fromImage(image)

    def make_cargo(self, preview, ext, pixel_art=False):
        """What he hauls: a preview on a white card (or a big pixel page) plus a type badge."""
        size = self.tier.cargo_px
        cargo = QPixmap(size, size)
        cargo.fill(Qt.transparent)
        p = QPainter(cargo)
        if preview:
            p.setRenderHint(QPainter.Antialiasing)
            frame = QRectF(1.5, 1.5, size - 3, size - 3)
            path = QPainterPath()
            path.addRoundedRect(frame, 6, 6)
            p.fillPath(path, QColor("white"))
            smooth = Qt.FastTransformation if pixel_art else Qt.SmoothTransformation
            img = preview.scaled(size - 10, size - 10, Qt.KeepAspectRatio, smooth)
            p.drawPixmap((size - img.width()) // 2, (size - img.height()) // 2, img)
            p.setPen(INK)
            p.drawPath(path)
        else:
            page = self.file_icon.scaled(size, size, Qt.KeepAspectRatio, Qt.FastTransformation)
            p.drawPixmap((size - page.width()) // 2, 0, page)
        # Type badge, e.g. "3MF", "PDF", "WEB".
        if ext:
            fm = QFontMetrics(BADGE_FONT)
            badge = QRect(0, 0, fm.horizontalAdvance(ext) + 10, 18)
            badge.moveTopLeft(QPoint(5, 5))  # top corner: never hidden by his claws
            p.setRenderHint(QPainter.Antialiasing)
            p.setBrush(QColor(226, 68, 46))
            p.setPen(INK)
            p.drawRoundedRect(badge, 4, 4)
            p.setFont(BADGE_FONT)
            p.setPen(QColor("white"))
            p.drawText(badge, Qt.AlignCenter, ext)
        p.end()
        return cargo

    def open_chat(self):
        self.last_poke = time.monotonic()
        self.mode = "chatting"
        self.bubble = None
        self.set_state("happy", 1)
        self.input.popup(self.geometry())

    def on_message(self, text):
        self.last_poke = time.monotonic()
        wants_quiet = MUTE_REQUEST.search(text)
        if wants_quiet or UNMUTE_REQUEST.search(text):  # "shut up" / "talk to me" work anywhere
            self.chat.add("you", escape(text))
            self.set_voice_on(not wants_quiet)
            self.history.append({"role": "user", "content": text})
            self.history.append({"role": "assistant", "content": self.bubble or ""})
            return
        if (self.mode in TASK_MODES and self.mode != "presenting") or self.mode == "thinking":
            self.reply(line("busy", self.settings["potty_mouth"]))
            return
        if BRAIN_REQUEST.search(text):  # "install ollama" / "check my specs": no brain needed
            self.chat.add("you", escape(text))
            self.history.append({"role": "user", "content": text})
            self.start_hardware_check()
            return
        self.card.hide()
        self.web_card.hide()
        self.history.append({"role": "user", "content": text})
        self.chat.add("you", escape(text))
        # An unmistakable "go get me a file" doesn't need a model to interpret it, and
        # waiting on one just makes him stand there. Anything vaguer still goes to the brain.
        if FETCH_REQUEST.search(text) and not WEB_HINTS.search(text):
            decision = RuleBrain().decide(self.history, self.settings["potty_mouth"])
            if decision.action == "find_files" and decision.query:
                self.reply(decision.text)
                self.start_search(decision.query)
                return
        self.mode = "thinking"
        brain, history, spicy = self.brain, list(self.history), self.settings["potty_mouth"]
        self.think_job = self.thinker.submit(brain.decide, history, spicy)

    def start_search(self, query, web_search=False):
        self.input.close_card()  # he's leaving; click him again to keep talking
        self.card.hide()
        self.web_card.hide()
        self.query = query
        self.web_mode = web_search
        self.mode = "roam"  # so floor_rect() reads his current screen before pinning it
        self.task_floor = self.floor_rect()
        self.home_x = self.clamp_x(self.x_pos)
        self.target_x = self.clamp_x(self.home_x + 160)
        self.mode = "searching"
        self.mode_until = time.monotonic() + MIN_SEARCH_S
        self.speak("searching_web" if web_search else "searching", 60)
        self.previews = {}
        if web_search:
            self.search_job = self.net.submit(web.search, query)
            return
        index = self.index
        self.search_job = self.worker.submit(
            lambda: (index.build() if index.stale else index).search(query)
        )

    def on_click(self):
        self.last_poke = time.monotonic()
        if self.input.isVisible():
            self.input.close_card()
        elif self.mode in ("thinking", "searching", "found", "exiting", "offscreen", "returning"):
            self.speak("busy", 1.5)
        elif self.state == "sleep":
            self.speak("wake", 1.5)
            self.set_state("idle", 1.5)
            QTimer.singleShot(900, self.open_chat)
        else:
            self.open_chat()

    # --- painting ------------------------------------------------------------

    def update_mask(self):
        """Only the crab, bubble and carried file catch clicks; the rest is click-through."""
        # While fetching, hide whatever pokes past the edge of his screen, so he
        # vanishes at the edge instead of appearing on a neighbouring monitor.
        clip = None
        if self.mode in TASK_MODES and self.task_floor is not None:
            clip = self.task_floor.translated(-int(self.x_pos), -int(self.y_pos))
            if clip.contains(self.rect()):
                clip = None
        key = (self.state, self.frame, self.bubble, self.carrying, self.carry_on_right,
               None if clip is None else clip.getRect())
        if key == self._mask_key:
            return
        self._mask_key = key
        region = QRegion(self.current_pixmap().mask()).translated(self.sprite_rect().topLeft())
        if self.bubble:
            region = region.united(QRegion(self.bubble_rect()))
        if self.carrying:
            cargo, label = self.carry_rects()
            region = region.united(QRegion(cargo.adjusted(-12, -12, 12, 2))).united(QRegion(label))
        if self.state in GAMING:
            region = region.united(QRegion(self.tv_rect()))
        if clip is not None:
            region = region.intersected(QRegion(clip))
            if region.isEmpty():
                region = QRegion(0, 0, 1, 1)  # an empty mask would mean "no mask" and show everything
        self.setMask(region)

    def paintEvent(self, _event):
        p = QPainter(self)
        if self.carrying:
            self.paint_cargo(p)
        if self.state in GAMING:
            self.paint_tv(p)
        p.drawPixmap(self.sprite_rect().topLeft(), self.current_pixmap())
        if self.bubble:
            rect = self.bubble_rect()
            self.paint_pill(p, rect, 10)
            p.setFont(BUBBLE_FONT)
            p.drawText(rect.adjusted(12, 7, -12, -7), Qt.TextWordWrap | Qt.AlignCenter, self.bubble)

    # --- gaming -------------------------------------------------------------

    def game_choices(self):
        return GAME_STYLES.get(self.settings.get("game_style", "both"), GAMING)

    def start_gaming(self, state=None):
        """Sit down facing the middle of the screen (so the TV is on-screen) and play."""
        state = state or random.choice(self.game_choices() or GAMING)
        center = self.x_pos + WIN_W / 2
        self.game_faces_left = center > self.floor_rect().center().x()
        self.set_state(state, random.uniform(*GAME_SECONDS))
        self.speak("game_start", 2.5)
        self.next_game_line = time.monotonic() + random.uniform(5, 9)

    def tv_rect(self):
        """The TV sits right in front of him, on the side he's facing."""
        size = self.tvs["game_retro"][0].size()
        sprite = self.sprite_rect()
        x = sprite.left() - size.width() + 4 if self.game_faces_left else sprite.right() - 4
        return QRect(x, WIN_H - size.height() - 2, size.width(), size.height())

    def paint_tv(self, p):
        key = self.state + ("_r" if self.game_faces_left else "")
        tv = self.tv_rect()
        p.drawPixmap(tv.topLeft(), self.tvs[key][self.frame % 4])
        if self.state == "game_retro":  # old-school wired controller
            sprite = self.sprite_rect()

            def at(rect, point):  # sprite pixel (drawn facing right) -> window coords
                x = SPRITE_PX - 1 - point[0] if self.game_faces_left else point[0]
                return QPointF(rect.left() + x * SCALE + SCALE / 2, rect.top() + point[1] * SCALE)

            start, end = at(sprite, CORD_FROM), at(tv, CORD_TO)
            cord = QPainterPath(start)
            cord.quadTo(QPointF((start.x() + end.x()) / 2, max(start.y(), end.y()) + 18), end)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QPen(QColor(40, 40, 45), 2))
            p.drawPath(cord)

    def paint_cargo(self, p):
        cargo, label = self.carry_rects()
        p.setRenderHint(QPainter.Antialiasing)
        moving = self.state in ("walk", "pull") and self.speed > 0.3

        # Dust kicked up behind heavy files.
        if self.tier.dust and moving:
            p.setPen(Qt.NoPen)
            back = cargo.right() + 4 if self.carry_on_right else cargo.left() - 4
            away = 1 if self.carry_on_right else -1
            for i in range(3):
                r = 4 + (self.frame + i) % 4 * 2
                p.setBrush(QColor(170, 150, 130, 140 - i * 35))
                p.drawEllipse(QPointF(back + away * i * 9, WIN_H - 6 - i * 3), r, r * 0.7)

        # The file rocks on its bottom edge as he tugs (or bounces overhead).
        pivot = QPointF(cargo.center().x(), cargo.bottom())
        rock = QTransform().translate(pivot.x(), pivot.y()).rotate(self.wobble).translate(-pivot.x(), -pivot.y())

        if not self.held:
            # Lead rope: claw -> knot on the near side of the lasso. Sags when he rests.
            band_y = cargo.top() + cargo.height() * 0.45
            near_x = cargo.left() if self.carry_on_right else cargo.right()
            knot = rock.map(QPointF(near_x, band_y))
            claw = self.rope_claw()
            sag = 3 + 16 * (1 - self.effort)
            lead = QPainterPath(claw)
            lead.quadTo(QPointF((claw.x() + knot.x()) / 2, max(claw.y(), knot.y()) + sag), knot)
            self.paint_rope(p, lead)

        p.save()
        p.setTransform(rock, True)
        p.drawPixmap(cargo.topLeft(), self.cargo)
        if not self.held:
            self.paint_lasso(p, cargo, band_y, near_x)
        p.restore()

        # Name + size tag.
        self.paint_pill(p, label, 6)
        p.setFont(LABEL_FONT)
        tag = self.carry_tag
        p.drawText(label, Qt.AlignCenter, QFontMetrics(LABEL_FONT).elidedText(tag, Qt.ElideMiddle, label.width() - 8))

    def paint_lasso(self, p, cargo, band_y, near_x):
        """A loop of rope cinched around the file, with a knot on his side."""
        left, right = cargo.left() - 3, cargo.right() + 3
        # Back of the loop peeks out past both edges...
        for x, bulge in ((left, -5), (right, 5)):
            back = QPainterPath(QPointF(x, band_y - 4))
            back.quadTo(QPointF(x + bulge, band_y), QPointF(x, band_y + 4))
            self.paint_rope(p, back, 4)
        # ...and the front wraps across, bowing down a touch like it's pulled tight.
        front = QPainterPath(QPointF(left, band_y - 3))
        front.quadTo(QPointF(cargo.center().x(), band_y + 7), QPointF(right, band_y - 3))
        self.paint_rope(p, front, 5)
        # Knot where the lead rope ties on.
        p.setPen(QPen(ROPE_DARK, 1.5))
        p.setBrush(ROPE)
        for dx, dy, r in ((0, 0, 5), (-3 if near_x > cargo.center().x() else 3, 4, 3.5)):
            p.drawEllipse(QPointF(near_x + dx, band_y + dy), r, r)

    @staticmethod
    def paint_rope(p, path, width=5):
        """Braided rope: dark edge, tan core, and a dashed strand pattern."""
        p.setBrush(Qt.NoBrush)
        for color, w, dash in ((ROPE_DARK, width + 2, None), (ROPE, width, None),
                               (ROPE_STRAND, max(1.0, width - 3), [1.2, 2.0])):
            pen = QPen(color, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            if dash:
                pen.setDashPattern(dash)
            p.strokePath(path, pen)

    @staticmethod
    def paint_pill(p, rect, radius):
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect).adjusted(1, 1, -1, -1), radius, radius)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillPath(path, QColor(255, 255, 255, 235))
        p.setPen(INK)
        p.drawPath(path)

    def toggle_potty_mouth(self):
        self.settings["potty_mouth"] = not self.settings["potty_mouth"]
        save_settings(self.settings)
        self.say("Oh, fuck yes." if self.settings["potty_mouth"] else "Fine. I'll be nice.", 2)

    # --- mouse ---------------------------------------------------------------

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.drag_offset = e.globalPosition().toPoint() - self.pos()
            self.drag_moved = False

    def mouseMoveEvent(self, e):
        if self.drag_offset is None:
            return
        new_pos = e.globalPosition().toPoint() - self.drag_offset
        if (new_pos - self.pos()).manhattanLength() > 3:
            self.drag_moved = True
        if self.drag_moved:
            self.x_pos, self.y_pos = float(new_pos.x()), float(new_pos.y())
            self.move(new_pos)
            if self.bubble is None:
                self.speak("picked_up", 1.2)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or self.drag_offset is None:
            return
        self.drag_offset = None
        self.last_poke = time.monotonic()
        if self.drag_moved:
            self.falling = self.y_pos < self.floor_y()
            self.fall_speed = 0.0
            if not self.falling:
                self.y_pos = float(self.floor_y())
            if self.mode == "roam":
                self.set_state("idle", 2)
        else:
            self.on_click()

    def fill_menu(self, menu):
        """His menu: used for right-clicking him and for the menu bar / tray icon."""
        menu.clear()

        def add(label, handler, checked=None):
            action = QAction(label, menu)
            action.triggered.connect(handler)
            if checked is not None:
                action.setCheckable(True)
                action.setChecked(checked)
            menu.addAction(action)
            return action

        add("Talk…", self.open_chat)
        add("Chat history", lambda: self.chat.popup(self.geometry()))
        add("Take a nap", lambda: self.set_state("sleep"))
        add("Play a game now", self.play_now)
        menu.addSeparator()

        brains = menu.addMenu("Brain")
        current_brain = self.settings.get("brain", "local")
        installed = available_brains()
        sections = [("local", "Local AI (private, offline)")]
        sections += [(key, f"{label} (your login · sends chats to {'Anthropic' if key == 'claude' else 'OpenAI'})")
                     for key, label in CLI_BRAINS.items()]
        for kind, title in sections:
            if (kind in CLI_BRAINS and kind not in installed) or (kind == "local" and not find_ollama()):
                if kind == "local":  # he can do this one himself
                    continue
                get = QAction(f"Get {CLI_BRAINS[kind]}…  (not installed)", brains)
                get.triggered.connect(lambda _c, k=kind: self.open_install_page(k))
                brains.addAction(get)
                continue
            sub = brains.addMenu(("✓ " if kind == current_brain else "") + title)
            picked = self.models().get(kind)
            options = model_options(kind)
            if kind == "local":
                auto = QAction("Auto (best for this computer's RAM)", sub, checkable=True,
                               checked=kind == current_brain and not picked)
                auto.triggered.connect(lambda _c: self.set_local_auto())
                sub.addAction(auto)
            elif not picked and options:
                picked = options[0][0] if kind == "claude" else options[-1][0]  # defaults: Haiku / Codex's pick
            for model, label, _score in reversed(options):  # smartest first
                action = QAction(label, sub, checkable=True, checked=kind == current_brain and model == picked)
                action.triggered.connect(lambda _c, k=kind, m=model: self.set_brain(k, m))
                sub.addAction(action)
        brains.addSeparator()
        add_brain = QAction(("Find me a brain 🔍  (Ollama not installed)" if not find_ollama()
                             else "Check my hardware 🔍"), brains)
        add_brain.triggered.connect(lambda _c: self.start_hardware_check())
        brains.addAction(add_brain)
        off = QAction("Keywords only (no AI)", brains, checkable=True, checked=current_brain == "keywords")
        off.triggered.connect(lambda _c: self.set_brain("keywords"))
        brains.addAction(off)

        games = menu.addMenu("Idle games")
        current = self.settings.get("game_style", "both")
        for key, label in (("both", "Both (random)"), ("retro", "Retro: CRT TV + beanbag"),
                           ("modern", "Modern: flat screen + gaming chair"), ("off", "Off")):
            action = QAction(label, games, checkable=True, checked=key == current)
            action.triggered.connect(lambda _checked, k=key: self.set_game_style(k))
            games.addAction(action)

        add(f"Check for updates…  (v{update.VERSION})", self.check_for_updates)
        add("Show crab" if not self.isVisible() else "Hide crab", self.toggle_hidden)
        voices = menu.addMenu("Voice: " + (self.voice.current_name() if self.voice.enabled else "Off 🔇"))
        off = QAction("🔇 Off (silent)", voices, checkable=True, checked=not self.voice.enabled)
        off.triggered.connect(lambda _c: self.set_voice_on(False))
        voices.addAction(off)
        voices.addSeparator()
        for v in self.voice.voices():
            action = QAction(v.name(), voices, checkable=True,
                             checked=self.voice.enabled and v.name() == self.voice.current_name())
            action.triggered.connect(lambda _c, name=v.name(): self.set_voice(name))
            voices.addAction(action)
        add("Potty mouth 🤬", self.toggle_potty_mouth, self.settings["potty_mouth"])
        menu.addSeparator()
        add("Quit Pixel Buddy", QApplication.quit)
        return menu

    def open_install_page(self, kind):
        QDesktopServices.openUrl(QUrl(INSTALL_PAGES[kind]))
        self.say("Install it, then restart me and pick it under Brain.", 5)

    def maybe_suggest_upgrade(self):
        """Once, on a fresh setup: tell people how to make him smarter."""
        if self.settings.get("upgrade_tip_shown") or available_brains():
            return
        keyword_only = isinstance(self.brain, RuleBrain) and self.settings.get("brain") != "keywords"
        if keyword_only or self.settings.get("brain", "local") == "local":
            self.settings["upgrade_tip_shown"] = True
            save_settings(self.settings)
            tip = "no_ollama_offer" if not find_ollama() else "no_ai_tip" if keyword_only else "smarter_tip"
            QTimer.singleShot(6000, lambda: self.speak(tip, 10))

    def set_local_auto(self):
        self.models().pop("local", None)
        self.set_brain("local")

    def set_voice_on(self, on):
        self.settings["voice_on"] = on
        save_settings(self.settings)
        if not on:
            self.voice.stop()
        self.speak("voice_on" if on else "voice_off", 3)

    def set_voice(self, name):
        """Picking a voice also turns talking back on."""
        self.settings["voice_name"] = name
        self.settings["voice_on"] = True
        save_settings(self.settings)
        self.voice.use(name)
        self.speak("new_voice", 3)

    def set_game_style(self, key):
        self.settings["game_style"] = key
        save_settings(self.settings)
        if key == "off" and self.state in GAMING:
            self.set_state("idle", 2)

    def play_now(self):
        if self.mode not in ("roam", "chatting"):
            self.speak("busy", 1.5)
            return
        self.mode = "roam"
        self.start_gaming()

    def contextMenuEvent(self, e):
        self.fill_menu(QMenu(self)).exec(e.globalPos())

    def toggle_hidden(self):
        if self.isVisible():
            for window in (self, self.input, self.card, self.web_card, self.model_card, self.chat):
                window.hide()
        else:
            self.show()
            self.speak("wake", 2)

    def open_chat_from_tray(self):
        if not self.isVisible():
            self.show()
        self.open_chat()

    def add_tray_icon(self):
        """A crab in the menu bar (Mac) / system tray (Windows): the always-findable way
        to talk to him, hide him, or quit."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(QIcon(self.frames["idle"][0]), self)
        self.tray.setToolTip("Pixel Buddy")
        self.tray_menu = QMenu()
        self.tray_menu.aboutToShow.connect(lambda: self.fill_menu(self.tray_menu))
        self.fill_menu(self.tray_menu)
        self.tray.setContextMenu(self.tray_menu)
        # Windows: left-click the tray crab to talk (right-click shows the menu).
        self.tray.activated.connect(
            lambda reason: reason == QSystemTrayIcon.Trigger and sys.platform != "darwin"
            and self.open_chat_from_tray())
        self.tray.show()


INSTANCE_NAME = "pixel-buddy-crab"


def already_running():
    """If a crab is already up, poke it (it opens its chat) and return True."""
    sock = QLocalSocket()
    sock.connectToServer(INSTANCE_NAME)
    if not sock.waitForConnected(300):
        return False
    sock.write(b"chat")
    sock.waitForBytesWritten(300)
    return True


def listen_for_pokes(buddy):
    """Second launches connect here instead of starting another crab."""
    QLocalServer.removeServer(INSTANCE_NAME)  # clear a stale socket from a crash
    server = QLocalServer(buddy)
    server.listen(INSTANCE_NAME)

    def on_connection():
        conn = server.nextPendingConnection()
        conn.readyRead.connect(lambda: (conn.readAll(), buddy.open_chat()))

    server.newConnection.connect(on_connection)


def log_to_file():
    """The packaged app has no terminal: send errors to a log file instead."""
    if not getattr(sys, "frozen", False):
        return
    if sys.platform == "darwin":
        log = Path.home() / "Library" / "Logs" / "pixel-buddy.log"
    else:
        log = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PixelBuddy" / "pixel-buddy.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    sys.stdout = sys.stderr = open(log, "a", buffering=1, encoding="utf-8")


def main():
    log_to_file()
    app = QApplication(sys.argv)
    if already_running():
        sys.exit(0)
    app.setQuitOnLastWindowClosed(False)  # hiding the card must not quit the app
    for sig in (signal.SIGINT, signal.SIGTERM):  # Ctrl+C / kill / logout quit cleanly
        signal.signal(sig, lambda *_: app.quit())
    buddy = Buddy()
    listen_for_pokes(buddy)
    buddy.add_tray_icon()
    buddy.show()
    buddy.speak("hello", 4)
    code = app.exec()
    stop_server()  # only stops Ollama if he started it
    # Exit now: don't wait on a half-finished file scan or web request in a worker thread.
    os._exit(code)


if __name__ == "__main__":
    main()
