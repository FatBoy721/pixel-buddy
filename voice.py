"""His voice: reads his speech bubbles out loud with the system's own voices
(Mac: AVSpeech voices like Junior/Rocko/Zarvox; Windows: SAPI/OneCore voices),
plus a handful of online neural voices (Microsoft Edge's TTS service) for
when you want something that doesn't sound like a robot crab.
Local voices need no extra downloads and work offline; the online ones need
internet and quietly fall back to the local voice if a request fails."""

import asyncio
import os
import re
import tempfile

from PySide6.QtCore import QThread, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtTextToSpeech import QTextToSpeech

try:
    import edge_tts
except ImportError:
    edge_tts = None

# Mac novelty voices that suit a tiny crab, best first; otherwise the system default.
CRAB_VOICES = ("Junior", "Rocko", "Eddy", "Fred")
PITCH = 0.45   # -1..1: higher = smaller crab
RATE = 0.1     # -1..1

# A handful of Microsoft Edge neural voices worth offering alongside whatever's
# installed locally. Label shown in the menu -> edge-tts voice id.
ONLINE_VOICES = {
    "Aria (online)": "en-US-AriaNeural",
    "Guy (online)": "en-US-GuyNeural",
    "Ana (online, kid-like)": "en-US-AnaNeural",
    "Jenny (online)": "en-US-JennyNeural",
    "Ryan (online, British)": "en-GB-RyanNeural",
    "Sonia (online, British)": "en-GB-SoniaNeural",
    "Natasha (online, Australian)": "en-AU-NatashaNeural",
}
ONLINE_RATE = "+10%"  # a little quick, to match the local RATE bias above


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


def _engine():
    """Prefer the winrt backend on Windows: it sees the OneCore voices
    (e.g. Mark) that the older sapi backend misses. Falls back to the
    platform default (sapi on Windows, the system engine elsewhere)."""
    available = QTextToSpeech.availableEngines()
    for name in ("winrt", "sapi"):
        if name in available:
            return QTextToSpeech(name)
    return QTextToSpeech()


class _OnlineVoice:
    """Stands in for a QVoice in the voice menu; only .name() is ever called."""
    def __init__(self, label):
        self._label = label

    def name(self):
        return self._label


class _EdgeSpeech(QThread):
    """Synthesizes one line with edge-tts (a network call) on a worker thread
    and reports back the mp3 file it wrote."""
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, text, voice_id):
        super().__init__()
        self.text = text
        self.voice_id = voice_id

    def run(self):
        fd, path = tempfile.mkstemp(suffix=".mp3", prefix="pixelbuddy_voice_")
        os.close(fd)
        try:
            asyncio.run(edge_tts.Communicate(self.text, self.voice_id, rate=ONLINE_RATE).save(path))
            self.done.emit(path)
        except Exception as e:
            try:
                os.remove(path)
            except OSError:
                pass
            self.failed.emit(str(e))


class Voice:
    def __init__(self, settings):
        self.settings = settings
        self.tts = _engine()
        self.tts.setPitch(PITCH)
        self.tts.setRate(RATE)
        self._player = QMediaPlayer()
        self._audio_out = QAudioOutput()
        self._player.setAudioOutput(self._audio_out)
        self._player.mediaStatusChanged.connect(self._cleanup_played_file)
        self._playing_path = None
        self._workers = set()  # keeps in-flight QThreads alive until they finish
        self._worker = None    # the one whose result we still want
        self._online_voice = None  # edge-tts voice id currently selected, or None
        self.use(settings.get("voice_name"))

    @property
    def enabled(self):
        return self.settings.get("voice_on", True)

    def _local_voices(self):
        found = [v for v in self.tts.availableVoices() if v.locale().name().startswith("en")]
        return sorted(found, key=lambda v: v.name())

    def voices(self):
        """English voices, local and online, sorted by name (the menu lists these)."""
        online = [_OnlineVoice(label) for label in ONLINE_VOICES] if edge_tts else []
        return sorted([*self._local_voices(), *online], key=lambda v: v.name())

    def current_name(self):
        if self._online_voice:
            return next(label for label, vid in ONLINE_VOICES.items() if vid == self._online_voice)
        return self.tts.voice().name()

    def use(self, name=None):
        if edge_tts and name in ONLINE_VOICES:
            self._online_voice = ONLINE_VOICES[name]
            return
        self._online_voice = None
        voices = {v.name(): v for v in self._local_voices()}
        pick = name if name in voices else next((n for n in CRAB_VOICES if n in voices), None)
        if pick:
            self.tts.setVoice(voices[pick])

    def say(self, text):
        if not self.enabled:
            return
        words = speakable(text)
        if not words:
            return
        self.stop()  # newest line wins; no backlog of old grunts
        if self._online_voice:
            worker = _EdgeSpeech(words, self._online_voice)
            self._worker = worker
            self._workers.add(worker)
            worker.done.connect(lambda path, w=worker: self._play(path, w))
            worker.failed.connect(lambda _err, w=worker: self._fallback(words, w))
            worker.finished.connect(lambda w=worker: self._workers.discard(w))
            worker.start()
        else:
            self.tts.say(words)

    def _play(self, path, worker):
        if worker is not self._worker:
            self._discard(path)  # a newer line or a stop() already won
            return
        self._playing_path = path
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()

    def _fallback(self, words, worker):
        if worker is self._worker:  # still the line we want to say
            self.tts.say(words)

    def _cleanup_played_file(self, status):
        done = (QMediaPlayer.MediaStatus.EndOfMedia, QMediaPlayer.MediaStatus.InvalidMedia)
        if status in done and self._playing_path:
            self._release_and_discard(self._playing_path)
            self._playing_path = None

    def _release_and_discard(self, path):
        # Windows' media backend keeps the file locked briefly after playback
        # ends; clearing the source releases it, but not always instantly.
        self._player.setSource(QUrl())
        self._discard(path, retries=5)

    def _discard(self, path, retries=0):
        try:
            os.remove(path)
        except OSError:
            if retries > 0:
                QTimer.singleShot(200, lambda: self._discard(path, retries - 1))

    def stop(self):
        self.tts.stop()
        self._player.stop()
        self._worker = None  # any result still in flight gets discarded as stale
        if self._playing_path:
            self._release_and_discard(self._playing_path)
            self._playing_path = None
