# Seasons: Halloween first

## Goal
The crab dresses up and acts differently around holidays, building up as the day gets close. Halloween ships first (by Oct 31, 2026); the same system takes Christmas and others later with no new plumbing.

## How a season plays out
Each season has a month, a countdown start, and a day. Halloween: October, Oct 25, Oct 31.

| Level | Halloween dates | Look | Halloween activity chance (per idle break) | Extras |
|---|---|---|---|---|
| month | Oct 1-24 | witch hat on every frame | 25% | - |
| countdown | Oct 25-30 | witch hat | 50% | countdown line ("3 days till Halloween!") once per wake/hello |
| day | Oct 31 | witch hat | 100% | 1 in 3 pokes plays BOO before opening chat; spooky hello |

Outside the month: no season, crab is exactly as today.

## Pieces

### 1. `seasons.py` (new, pure, no Qt)
- `SEASONS = {"halloween": Season(month=10, countdown_from=25, day=31)}`
- `current(today, override) -> (name | None, level | None, days_left)`; `override` is `"auto"`, `"off"`, or a season name (forced season acts as level `day` so everything is visible when testing).
- `__main__` assert-based self-check: Oct 1 -> month, Oct 25 -> countdown (6 left), Oct 31 -> day, Nov 1 -> None, override "off" -> None, override "halloween" in July -> day.

### 2. `make_sprites.py`
- Witch hat: a `hat(c, bob)` details function (purple/black cone, orange band, tilted), sitting between the eye stalks and moving with `bob`.
- For each season, re-render every existing state with the hat into `assets/halloween/<state>_N.png`. States that already wear headgear (sleep nightcap, gaming headset) keep their own and skip the hat.
- New Halloween-only states, each 4 frames, in `assets/halloween/`:
  - `carve`: crab behind a pumpkin, scraping; last frames show the lit jack-o'-lantern.
  - `ghost`: crab under a sheet (two eye holes, legs showing), bobbing.
  - `boo`: ducks into a pumpkin, then pops out with arms up.
- Preview sheet gets a second row for the Halloween set.

### 3. `buddy.py`
- `load_frames(season)`: load `assets/<season>/<state>_N.png` when present, else fall back to `assets/<state>_N.png`. Reloaded once a day (date check in the existing tick) and when the override changes.
- `pick_next_action`: before the gaming roll, roll the level's activity chance and pick `carve` or `ghost` for 15-30 s.
- `on_click`: on level `day`, 1 in 3 pokes plays `boo` (about 1.2 s) with a "boo" line, then opens chat as usual.
- Right-click menu: `Season: Auto / Off / Halloween`, stored in settings as `season`.

### 4. `lines.py`
New keys in CLEAN (SPICY falls back as today, may add its own): `carve`, `ghost`, `boo`, `countdown` (uses `{n}`), `halloween_hello`.

## Out of scope (later)
Bats flying around, trick-or-treat walk, other holidays. Each is an add-on once this works.

## Testing
- `python seasons.py` self-check passes.
- `python make_sprites.py` writes the Halloween set; eyeball `assets/preview.png`.
- Run the app with Season forced to Halloween: hat visible in idle/walk/pull, carve and ghost appear, BOO plays on some pokes. Set Season to Off: crab back to normal.

## Addendum (2026-10-08): daily looks
The outfit rotates daily through October by date: `(day - 1) % 4` over witch, slasher, hockey, screamer (Oct 31 = hockey). Art lives in `assets/halloween/<look>/` (hatted states, carve, boo); the ghost is shared in `assets/halloween/`. Lookalike costumes only; the app never names the movie characters. Season menu can force any single look (`halloween/<look>`). Costume looks get their own hello lines half the time.
