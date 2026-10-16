# Seasons: Halloween Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The crab wears a witch hat in October, gets more Halloween-y as Oct 31 nears, and has three new Halloween animations (carve, ghost, boo).

**Architecture:** A pure `seasons.py` decides (season, level, days_left) from the date and a user override. `make_sprites.py` bakes a second sprite set into `assets/halloween/` (hatted copies of the plain crab frames + 3 new states). `buddy.py` loads `assets/<season>/` with fallback to `assets/`, rolls Halloween activities by level, and adds a Season menu.

**Tech Stack:** Python 3, PySide6, Pillow (dev-time only, for sprites).

**Spec:** `docs/superpowers/specs/2026-10-08-seasons-halloween-design.md`

## Global Constraints
- Outside the season month with override `auto`, the crab must behave and look exactly as today.
- Halloween: month 10, countdown from day 25, day 31.
- Activity chance per idle break: month 25%, countdown 50%, day 100%.
- BOO: 1 in 3 pokes, only at level `day`, then chat opens as usual.
- Forced season (override = season name) acts as level `day`.
- Pillow stays dev-only (packaging excludes `PIL` and `make_sprites`); the app only reads PNGs.
- User runs all git commands himself: steps end with the exact commands for him, not executed by the agent.

## Review Focus
- App started on Oct 31 at 23:59 and left running past midnight: season must drop on Nov 1 without restart (Task 4 daily recheck).
- Season switched to Off while crab is mid-`ghost`: he must return to idle, not crash on a missing frame key (Task 4 `refresh_season`).
- `assets/halloween/` missing (fresh clone without running make_sprites): app must still start, just without Halloween (Task 4 fallback + `"carve" in self.frames` guards).
- Countdown text with 1 day left must read "1 day", not "1 days" (Task 3 `days` formatting).
- Poke during a non-roam mode (searching, thinking) on Oct 31: existing busy line, no BOO (Task 4 BOO lives only in the final `else`).

---

### Task 1: `seasons.py`

**Files:** Create `seasons.py`

**Interfaces:**
- Produces: `SEASONS: dict[str, Season]`, `ACTIVITY_CHANCE: dict[str, float]`, `current(today: date, override: str = "auto") -> tuple[str | None, str | None, int]`

- [ ] **Step 1: Write the module with its self-check**

```python
"""Which holiday is it, and how close? Pure date logic, no Qt.

Each season builds up: the whole month (light), a countdown week (more),
then the day itself (full)."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Season:
    month: int
    countdown_from: int  # day of month the countdown level starts
    day: int             # the holiday itself


SEASONS = {"halloween": Season(month=10, countdown_from=25, day=31)}
ACTIVITY_CHANCE = {"month": 0.25, "countdown": 0.5, "day": 1.0}


def current(today, override="auto"):
    """-> (season name, level, days left). (None, None, 0) when no season applies.
    override: "auto", "off", or a season name (forced = level "day", for testing)."""
    if override == "off":
        return None, None, 0
    if override in SEASONS:
        return override, "day", 0
    for name, s in SEASONS.items():
        left = s.day - today.day
        if today.month == s.month and left >= 0:
            level = "day" if left == 0 else "countdown" if today.day >= s.countdown_from else "month"
            return name, level, left
    return None, None, 0


if __name__ == "__main__":
    assert current(date(2026, 10, 1)) == ("halloween", "month", 30)
    assert current(date(2026, 10, 24)) == ("halloween", "month", 7)
    assert current(date(2026, 10, 25)) == ("halloween", "countdown", 6)
    assert current(date(2026, 10, 30)) == ("halloween", "countdown", 1)
    assert current(date(2026, 10, 31)) == ("halloween", "day", 0)
    assert current(date(2026, 11, 1)) == (None, None, 0)
    assert current(date(2026, 9, 30)) == (None, None, 0)
    assert current(date(2026, 10, 31), "off") == (None, None, 0)
    assert current(date(2026, 7, 4), "halloween") == ("halloween", "day", 0)
    assert current(date(2026, 7, 4), "nonsense") == (None, None, 0)
    print("seasons ok")
```

- [ ] **Step 2: Run it**

Run: `.venv\Scripts\python seasons.py`
Expected: `seasons ok`

- [ ] **Step 3: Commit (user runs)** `git add seasons.py && git commit -m "Seasons: date logic for holiday build-up"`

---

### Task 2: Halloween sprites

**Files:** Modify `make_sprites.py` (`draw_crab` end ~line 196, `FRAMES` ~line 604, `main` ~line 709)

**Interfaces:**
- Produces: PNGs `assets/halloween/{walk,idle,happy,confused,pull,peek}_N.png` (same frame counts as base) and `assets/halloween/{carve,ghost,boo}_0..3.png`.

- [ ] **Step 1: Add a module-level hat hook to `draw_crab`**

Above `draw_crab` add `HAT = None  # set to a hat(c, bob, lean) function while baking a season`. At the very end of `draw_crab`, just before `return c.image()`:

```python
    if HAT:
        HAT(c, bob, lean)
```

- [ ] **Step 2: Add colors, the witch hat, a pumpkin helper, and the new states** (new section after the gaming section)

```python
# --- halloween -------------------------------------------------------------------

HAT_BLACK = (40, 28, 52, 255)
HAT_PURPLE = (92, 52, 140, 255)
HAT_BAND = (255, 140, 30, 255)
PUMPKIN = (240, 120, 20, 255)
PUMPKIN_DARK = (190, 80, 10, 255)
STEM = (70, 120, 40, 255)
GLOW = (255, 220, 80, 255)
SHEET = (236, 236, 246, 255)
SHEET_SHADE = (196, 196, 214, 255)


def witch_hat(c, bob, lean):
    """Tilted witch hat between the eye stalks. Drawn on its own layer, outlined,
    then stamped on top so it never merges into the shell outline."""
    layer = Canvas()
    for x in range(11, 21):
        layer.set(x, 13 + bob, HAT_BLACK)                       # brim
    for x in range(14, 18):
        layer.set(x, 12 + bob, HAT_BAND)                        # band
    cone = {11: (14, 17), 10: (15, 16), 9: (15, 16), 8: (15, 16), 7: (16, 16), 6: (16, 17), 5: (17, 17)}
    for y, (x0, x1) in cone.items():
        for x in range(x0, x1 + 1):
            layer.set(x, y + bob, HAT_PURPLE if x == x0 else HAT_BLACK)
    layer.outline()
    for y in range(SIZE):
        for x in range(SIZE):
            if layer.px[y][x] != CLEAR and 0 <= x + lean < SIZE:
                c.px[y][x + lean] = layer.px[y][x]


def pumpkin(c, cx, cy, rx, ry):
    """Round ribbed pumpkin with a stem, centered at (cx, cy)."""
    for y in range(SIZE):
        for x in range(SIZE):
            if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1:
                c.set(x, y, PUMPKIN_DARK if abs(x - cx) in (rx // 2, rx // 2 + 1) else PUMPKIN)
    c.set(int(cx), int(cy - ry), STEM)
    c.set(int(cx) + 1, int(cy - ry) - 1, STEM)


def jack_face(c, cx, cy, lit=True):
    """Carved face, drawn after outlining so it stays crisp."""
    color = GLOW if lit else OUTLINE
    for dx, dy in ((-3, -2), (-2, -2), (-3, -1), (2, -2), (3, -2), (3, -1)):   # eyes
        c.set(int(cx) + dx, int(cy) + dy, color)
    for dx in range(-3, 4):                                                     # grin
        c.set(int(cx) + dx, int(cy) + 2 - (dx in (-3, 3)), color)


def draw_carve(frame):
    """Behind a pumpkin, scraping at it; the face appears on the last two frames."""
    return draw_crab(bob=frame % 2, claw=CLAW_HALF if frame % 2 else CLAW_OPEN, claw_lift=frame % 2,
                     props=lambda c, bob: pumpkin(c, 15.5, 23, 8, 5),
                     details=(lambda c, bob: jack_face(c, 15.5, 23, lit=frame == 3)) if frame >= 2 else None)


def draw_ghost(frame):
    """Sheet over his head: two eye holes, wavy hem, his legs poking out. Floats."""
    c = Canvas()
    lift = (0, 1, 2, 1)[frame]
    for i, (ax, ay) in enumerate(((10, 24), (12, 25), (14, 25))):          # legs under the hem
        for side in (0, 1):
            x = SIZE - 1 - ax if side else ax
            c.line(x, ay - lift, x, 27 - lift, SHELL_DARK, mirror=False)
    for y in range(SIZE):
        for x in range(SIZE):
            top = ((x - 15.5) / 8.5) ** 2 + ((y - 13 + lift) / 8) ** 2 <= 1 and y <= 13 - lift
            body = 7 <= x <= 24 and 13 - lift < y <= 22 - lift + ((x + frame) // 3) % 2
            if top or body:
                c.set(x, y, SHEET_SHADE if x >= 21 else SHEET)
    c.outline()
    for x, y in ((12, 11), (13, 11), (12, 12), (13, 12), (18, 11), (19, 11), (18, 12), (19, 12)):
        c.set(x, y - lift, PUPIL)                                            # eye holes
    return c.image()


def draw_boo(frame):
    """Ducks into a pumpkin, then pops out arms-up."""
    if frame == 0:   # only his eyes over the rim
        c = Canvas()
        pumpkin(c, 15.5, 22, 10, 6)
        c.outline()
        for x in (12, 13, 18, 19):
            c.set(x, 15, EYE_WHITE)
        c.set(13, 15, PUPIL)
        c.set(19, 15, PUPIL)
        return c.image()
    if frame == 1:   # hidden, pumpkin wobbles
        c = Canvas()
        pumpkin(c, 16.5, 22, 10, 6)
        c.outline()
        return c.image()
    return draw_crab(bob=-1 if frame == 2 else 0, eyes="happy", claw_lift=3 if frame == 2 else 2,
                     props=lambda c, bob: pumpkin(c, 15.5, 25, 10, 4))


HALLOWEEN_HATTED = ("walk", "idle", "happy", "confused", "pull", "peek")
```

- [ ] **Step 3: Make the frame table rebuildable**

Rename the `FRAMES = { ... }` literal to a function body:

```python
def build_frames():
    return {
        # ... the existing FRAMES dict contents, unchanged ...
    }


FRAMES = build_frames()
```

- [ ] **Step 4: Bake the Halloween set in `main()`**

After the existing `for name, frames in FRAMES.items(): ...` loop, before the preview sheet:

```python
    global HAT
    HAT = witch_hat
    halloween = {k: v for k, v in build_frames().items() if k in HALLOWEEN_HATTED}
    halloween |= {"carve": [draw_carve(f) for f in range(4)],
                  "ghost": [draw_ghost(f) for f in range(4)],
                  "boo": [draw_boo(f) for f in range(4)]}
    HAT = None
    (ASSETS / "halloween").mkdir(exist_ok=True)
    for name, frames in halloween.items():
        for i, frame in enumerate(frames):
            frame.save(ASSETS / "halloween" / f"{name}_{i}.png")
```

Replace the preview sheet block with a two-row sheet (row 0 = base, row 1 = Halloween):

```python
    rows = [[f for fs in FRAMES.values() for f in fs], [f for fs in halloween.values() for f in fs]]
    width = max(len(r) for r in rows)
    sheet = Image.new("RGBA", (SIZE * width, SIZE * 2), (200, 220, 235, 255))
    for row, frames in enumerate(rows):
        for i, frame in enumerate(frames):
            sheet.alpha_composite(frame, (i * SIZE, row * SIZE))
    sheet.resize((sheet.width * 8, sheet.height * 8), Image.NEAREST).save(ASSETS / "preview.png")
    print(f"Wrote {len(rows[0])} frames + {len(rows[1])} halloween frames to {ASSETS}")
```

- [ ] **Step 5: Bake and check**

Run: `.venv\Scripts\python make_sprites.py`
Expected: `Wrote 34 frames + 28 halloween frames to ...` (6 hatted states = 4+2+2+2+4+2 = 16, plus 12 new).
Then: `.venv\Scripts\python -c "from pathlib import Path; print(len(list(Path('assets/halloween').glob('*.png'))))"` -> `28`.
Also confirm base frames unchanged: `git diff --stat assets/` shows only `preview.png` modified among existing files (plus the new `halloween/` folder).

- [ ] **Step 6: Eyeball and tune**

Open `assets/preview.png`. Hat must sit on top of the shell between the eye stalks, not covering the eyes; pumpkin reads as a pumpkin; ghost reads as a sheet with legs. Adjust the pixel tables in Step 2 and re-run Step 5 until it looks right. Show the user the preview before moving on.

- [ ] **Step 7: Commit (user runs)** `git add make_sprites.py assets && git commit -m "Halloween sprites: witch hat, carving, ghost, boo"`

---

### Task 3: Halloween lines

**Files:** Modify `lines.py` (add to the `CLEAN` dict; SPICY falls back automatically via `line()`)

**Interfaces:**
- Produces keys: `carve`, `ghost`, `boo`, `countdown` (format arg `days`, e.g. "1 day" / "6 days"), `halloween_hello`.

- [ ] **Step 1: Add the keys to `CLEAN`**

```python
    "carve": ["Pumpkin surgery in progress.", "Hold still, gourd.", "Giving this guy a face."],
    "ghost": ["Ooooooo. I'm a ghost.", "Boo-hoo-hoo, spooky crab.", "You can't see me. I'm a sheet."],
    "boo": ["BOO!", "Gotcha! BOO!", "Rawr! Did I scare you?"],
    "countdown": ["{days} till Halloween!", "Halloween in {days}. I'm so ready.",
                  "{days} left. Costume's ready, are you?"],
    "halloween_hello": ["Happy Halloween! Click me if you dare.", "Trick or treat! Need a file found?"],
```

- [ ] **Step 2: Check every key formats**

Run: `.venv\Scripts\python -c "import lines; [print(lines.line(k, s, days='1 day')) for k in ('carve','ghost','boo','countdown','halloween_hello') for s in (False, True)]"`
Expected: 10 lines printed, no KeyError, countdown reads "1 day till Halloween!" style (singular).

- [ ] **Step 3: Commit (user runs)** `git add lines.py && git commit -m "Halloween lines"`

---

### Task 4: Wire seasons into the app

**Files:** Modify `buddy.py`: imports, `FRAME_MS` (~line 49), `load_frames` (~line 169), `__init__` (after settings load ~line 260), `tick` (~line 392 and ~408), `pick_next_action` (~line 504), `on_click` (~line 952), menu (after "Idle games" ~line 1230), startup hello (~line 1380).

**Interfaces:**
- Consumes: `seasons.current(date, override)`, `seasons.ACTIVITY_CHANCE`; PNGs from Task 2; line keys from Task 3.
- Produces: settings key `season` ("auto" | "off" | "halloween"); attributes `self.season`, `self.season_level`, `self.days_left`, `self.season_date`.

- [ ] **Step 1: Imports and frame timings**

Add `from datetime import date` and `import seasons` with the other imports. Under `FRAME_MS` add:

```python
SEASON_FRAME_MS = {"carve": 300, "ghost": 260, "boo": 220}  # only exist in a season's assets folder
SEASON_ACTIVITIES = ("carve", "ghost")
```

- [ ] **Step 2: Season-aware `load_frames`**

```python
def load_frames(season=None):
    frames = {}
    for name in (*FRAME_MS, *SEASON_FRAME_MS):
        paths = sorted((ASSETS / season).glob(f"{name}_*.png")) if season else []
        paths = paths or sorted(ASSETS.glob(f"{name}_*.png"))
        if not paths:
            if name in SEASON_FRAME_MS:
                continue  # no season art (or no season): just skip these states
            sys.exit(f"Missing sprites in {ASSETS}. Run: python make_sprites.py")
        frames[name] = [load_pixmap(p, SCALE) for p in paths]
    for name in ("pull", *GAMING):
        frames[name + "_r"] = mirrored(frames[name])
    return frames
```

In `tick`, change `frame_ms = FRAME_MS[self.state] * ...` to `frame_ms = {**FRAME_MS, **SEASON_FRAME_MS}[self.state] * ...`.

- [ ] **Step 3: `refresh_season` + daily recheck**

Add the method:

```python
    def refresh_season(self):
        """Pick today's season (or the forced one) and load its sprites."""
        self.season_date = date.today()
        self.season, self.season_level, self.days_left = seasons.current(
            self.season_date, self.settings.get("season", "auto"))
        self.frames = load_frames(self.season)
        if self.state not in self.frames:
            self.set_state("idle", 1)
        self.frame %= len(self.frames[self.state])
```

Call `self.refresh_season()` in `__init__` right after `self.settings = load_settings()` (the earlier `self.frames = load_frames()` stays as the boot default). At the top of `tick`, after `now = time.monotonic()`:

```python
        if date.today() != self.season_date:
            self.refresh_season()
```

- [ ] **Step 4: Halloween activities in `pick_next_action`**

Right after the sleep branch (`if time.monotonic() - self.last_poke > SLEEP_AFTER_S: ...`), insert as the next `elif`:

```python
        elif (self.season_level and "carve" in self.frames
              and random.random() < seasons.ACTIVITY_CHANCE[self.season_level]):
            state = random.choice(SEASON_ACTIVITIES)
            self.set_state(state, random.uniform(15, 30))
            self.speak(state, 2.5)
```

- [ ] **Step 5: BOO and countdown on poke**

In `on_click`, replace the sleep branch's `self.speak("wake", 1.5)` with `self.greet("wake", 1.5)`, and the final `else: self.open_chat()` with:

```python
        elif self.season_level == "day" and "boo" in self.frames and random.random() < 1 / 3:
            self.set_state("boo", 1.2)
            self.speak("boo", 1.5)
            QTimer.singleShot(1200, self.open_chat)
        else:
            self.open_chat()
```

Add the helper (also used at startup):

```python
    def greet(self, key, seconds):
        """Hello/wake line, swapped for a countdown or holiday line in season."""
        if self.season_level == "countdown":
            self.speak("countdown", seconds + 1, days=f"{self.days_left} day" + ("s" if self.days_left != 1 else ""))
        elif self.season_level == "day" and self.season == "halloween":
            self.speak("halloween_hello", seconds + 1)
        else:
            self.speak(key, seconds)
```

Also change the other `self.speak("wake", 2)` (~line 1304) to `self.greet("wake", 2)` and the startup `buddy.speak("hello", 4)` (~line 1380) to `buddy.greet("hello", 4)`.

- [ ] **Step 6: Season menu**

After the "Idle games" submenu block:

```python
        season_menu = menu.addMenu("Season")
        current_season = self.settings.get("season", "auto")
        for key, label in (("auto", "Auto (by date)"), ("off", "Off"), ("halloween", "Halloween")):
            action = QAction(label, season_menu, checkable=True, checked=key == current_season)
            action.triggered.connect(lambda _c, k=key: self.set_season(k))
            season_menu.addAction(action)
```

And the setter next to `set_game_style`:

```python
    def set_season(self, key):
        self.settings["season"] = key
        save_settings(self.settings)
        self.refresh_season()
```

- [ ] **Step 7: Offscreen smoke test**

Run:
```
.venv\Scripts\python -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; from PySide6.QtWidgets import QApplication; app=QApplication([]); import buddy; f=buddy.load_frames('halloween'); print(sorted(k for k in f if not k.endswith('_r'))); g=buddy.load_frames(None); print('carve' in g, 'idle' in g); h=buddy.load_frames('nonexistent'); print('idle' in h, 'carve' in h)"
```
Expected: first list includes `boo`, `carve`, `ghost`; then `False True`; then `True False`.

- [ ] **Step 8: Run the app and verify on screen**

Run `.venv\Scripts\python buddy.py`. Right-click → Season → Halloween:
1. Hat visible while idle and walking.
2. Within a few idle breaks he carves or goes ghost (forced = 100%).
3. Several pokes: roughly 1 in 3 plays BOO, then chat opens.
4. Right-click → Season → Off while he's a ghost: back to normal crab, no crash.
5. Season → Auto: today (Oct 8) = month level, hat on, Halloween breaks occasional.
Report what was and was not seen on screen.

- [ ] **Step 9: Commit (user runs)** `git add buddy.py && git commit -m "Seasons: Halloween build-up, activities, BOO, Season menu"`
