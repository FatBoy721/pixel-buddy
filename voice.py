"""His voice: reads his speech bubbles out loud with the system's own voices
(Mac: AVSpeech voices like Junior/Rocko/Zarvox; Windows: SAPI/OneCore voices).
No extra downloads, works offline."""

import re

from PySide6.QtTextToSpeech import QTextToSpeech

# Mac novelty voices that suit a tiny crab, best first; otherwise the system default.
CRAB_VOICES = ("Junior", "Rocko", "Eddy", "Fred")
PITCH = 0.45   # -1..1: higher = smaller crab
RATE = 0.1     # -1..1


def speakable(text):
    """What to actually say for a bubble, or "" to stay quiet."""
    text = text.replace("​", "")
    if not re.search(r"[A-Za-z0-9]", text) or re.fullmatch(r"[Zz]+", text.strip()):
        return ""  # thinking dots, Zzz
    # Paths are awful read aloud: "/Users/me/Documents/Jobs" -> "the Jobs folder".
    text = re.sub(r"(?:[A-Za-z]:)?[\\/](?:[^\s\\/]+[\\/])*([^\s\\/]+)[\\/]?",
                  lambda m: f"the {m.group(1)} folder", text)
    text = text.replace("*", "").replace("→", ",").replace("…", "...")
    return re.sub(r"[^\w\s.,!?'\"():;%-]", "", text).strip()


class Voice:
    def __init__(self, settings):
        self.settings = settings
        self.tts = QTextToSpeech()
        self.tts.setPitch(PITCH)
        self.tts.setRate(RATE)
        self.use(settings.get("voice_name"))

    @property
    def enabled(self):
        return self.settings.get("voice_on", True)

    def voices(self):
        """English voices, sorted by name (the menu lists these)."""
        found = [v for v in self.tts.availableVoices() if v.locale().name().startswith("en")]
        return sorted(found, key=lambda v: v.name())

    def current_name(self):
        return self.tts.voice().name()

    def use(self, name=None):
        voices = {v.name(): v for v in self.voices()}
        pick = name if name in voices else next((n for n in CRAB_VOICES if n in voices), None)
        if pick:
            self.tts.setVoice(voices[pick])

    def say(self, text):
        if not self.enabled:
            return
        words = speakable(text)
        if words:
            self.tts.stop()  # newest line wins; no backlog of old grunts
            self.tts.say(words)

    def stop(self):
        self.tts.stop()
