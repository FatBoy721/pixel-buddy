# Pixel Buddy 🦀

A pixel crab that wanders along the bottom of your screen.

## Run it

**Mac**
```bash
cd ~/pixel-buddy
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python buddy.py
```

**Windows** (PowerShell, with Python 3.10+ installed)
```powershell
cd pixel-buddy
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python buddy.py
```

## Controls
- **Click** him to open the chat. Just talk:
  - "where's my most recent resume" → he runs off and drags the file back
  - "what's up" or any question → he chats back
  - online stuff → he answers or offers to dig on the web, then reads the results
    and tells you what he found (with links)
- Close the chat: **✕**, **Esc**, **Enter on an empty box**, or click him again
- **Drag** him: pick him up; let go and he falls back down
- **Voice**: he reads his lines out loud. Right-click → **Voice** → **🔇 Off** to silence him,
  or pick a voice. Or just type **"shut up"** / **"mute"**, and **"unmute"** to bring it back.
- **Right-click** (or the 🦀 in the menu bar / tray): talk, chat history, nap, play a game,
  Brain, Idle games, Voice, Potty mouth, quit

## His brain (local AI, optional)
Runs 100% on your machine through [Ollama](https://ollama.com). He picks a model by RAM:

| RAM | Model | Download |
|---|---|---|
| 16 GB+ | `qwen3.5:4b` | 3.4 GB |
| 8–16 GB | `qwen3.5:2b` | 2.7 GB |
| under 8 GB | `qwen3:1.7b` (keywords pick actions, AI chats) | 1.4 GB |

### Or use Claude Code / Codex
Right-click → **Brain** → **Claude Code** or **Codex**. He finds the CLI if it's installed
and uses your existing login (Claude runs on Haiku to keep it quick and cheap). Their tools
are switched off: they only send back text, and he does the file/web work himself. These
send your chats to Anthropic / OpenAI; **Local AI** keeps everything on your machine.

Install one with e.g. `ollama pull qwen3.5:4b`. To force a model, set `"model"` in
`~/.pixel-buddy.json`. With no Ollama running he still works in keyword mode: file
and web searches work, chat doesn't.

## Previews
Images show themselves. 3D print files show their slicer thumbnail: `.3mf`
(Bambu/Orca/Prusa/Cura), `.gcode`, and `.bgcode`. `.stl` files get a quick
3D render. On Mac, everything else (PDF, Word, etc.) uses Quick Look.

## What he searches
File **names** in Desktop, Documents, Downloads, and OneDrive (skips hidden folders,
`node_modules`, Library, AppData). Words like *recent/latest/oldest* change the sort;
*pdf/photo/video/spreadsheet* filter by type.

## Change how he looks
Edit `make_sprites.py`, then run `python make_sprites.py`. `assets/preview.png` shows every frame.

## Quitting him
Click the **🦀 crab in the menu bar** (Mac) or **system tray** (Windows) → **Quit Pixel Buddy**.
Right-clicking him works too. That menu also has Talk, Chat history, and Hide/Show crab.

## Building the app
Build on each OS for that OS:
```bash
pip install -r requirements.txt pyinstaller
python packaging/make_icons.py
pyinstaller packaging/pixel_buddy.spec --noconfirm
```
Mac → `dist/Pixel Buddy.app` (menu bar app, no Dock icon).
Windows → `dist\Pixel Buddy\Pixel Buddy.exe`.
Logs: `~/Library/Logs/pixel-buddy.log` (Mac), `%LOCALAPPDATA%\PixelBuddy\pixel-buddy.log` (Windows).
