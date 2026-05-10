"""Game audio: ambient loops, engine music, crash (paths resolved from project root)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

_ROOT = Path(__file__).resolve().parent.parent


def _sound_path(name: str) -> Path:
    from . import config

    return _ROOT / config.ASSETS_DIR / "sound" / name


# Filenames under assets/sound/ — loaded on demand so menu ambience can start
# before decoding every MP3 (startup used to feel silent for seconds).
_SOUND_BANK: dict[str, str] = {
    "bg": "background.mp3",
    "reverse": "reverselambo.mp3",
    "crash": "Hitsound.mp3",
    "release": "slowreal.mp3",
    "nitro": "nitro.mp3",
    "slip": "driff.mp3",
    "lambo": "lamboreal02.mp3",
    "slow": "slow03.mp3",
}


class SoundManager:
    def __init__(self) -> None:
        import pygame

        self._pygame = pygame
        self.channels: Dict[str, Any] = {}
        self.sounds: Dict[str, Any] = {}
        self.current_music: Optional[str] = None

    def _ensure_loaded(self, *keys: str) -> None:
        import pygame

        for key in keys:
            if key in self.sounds:
                continue
            rel = _SOUND_BANK.get(key)
            if not rel:
                continue
            path = _sound_path(rel)
            if not path.is_file():
                continue
            try:
                self.sounds[key] = pygame.mixer.Sound(str(path))
            except Exception:
                pass

    def play_loop(self, name: str, volume: float) -> None:
        self._ensure_loaded(name)
        s = self.sounds.get(name)
        if s is None:
            return
        ch = s.play(-1)
        ch.set_volume(volume)
        self.channels[name] = ch

    def play_once(self, name: str) -> None:
        self._ensure_loaded(name)
        s = self.sounds.get(name)
        if s is not None:
            s.play()

    def music(self, name: str, volume: float) -> None:
        if self.current_music == name:
            return
        self._ensure_loaded(name)
        s = self.sounds.get(name)
        if s is None:
            self.current_music = None
            return
        self.stop_loop("engine")
        ch = s.play(-1)
        ch.set_volume(volume)
        self.channels["engine"] = ch
        self.current_music = name

    def stop_music(self) -> None:
        self.stop_loop("engine")
        self.current_music = None

    def stop_sound(self, name: str) -> None:
        """Stop every channel currently playing the named one-shot sound."""
        s = self.sounds.get(name)
        if s is None:
            return
        try:
            s.stop()
        except Exception:
            pass

    def stop_loop(self, name: str) -> None:
        """Stop a named looping channel (no-op if it wasn't started)."""
        ch = self.channels.get(name)
        if ch is not None:
            try:
                ch.stop()
            except Exception:
                pass
            self.channels.pop(name, None)

    def start_game_ambient(self) -> None:
        self.play_loop("bg", 0.5)
        self.play_loop("reverse", 0.25)

    def preload_gameplay_sounds(self) -> None:
        """Load engine beds and one-shots before first use (avoids hitch on gas-down).

        Ambient only loads ``bg`` / ``reverse``; ``lamboreal02`` is large and was
        previously decoded on the first throttle edge, which froze the frame loop.
        """
        self._ensure_loaded("lambo", "slow", "crash", "release", "nitro", "slip")

    def silence_gameplay(self) -> None:
        """Leave only the background music loop; kill everything else.

        Stops tracked loops (engine reverse), the engine bed channel, and
        any still-ringing one-shots (like the crash sound) by asking each
        Sound in the bank to stop on every channel it owns.
        """
        self.stop_music()
        for name in list(self.channels.keys()):
            if name != "bg":
                self.stop_loop(name)
        for name, snd in self.sounds.items():
            if name == "bg":
                continue
            try:
                snd.stop()
            except Exception:
                pass

    def resume_gameplay(self) -> None:
        """Restart gameplay loops without double-triggering the background."""
        # Background stays on across runs; only (re)start the engine loop if
        # we've silenced it earlier (e.g. after a previous game over).
        if "reverse" not in self.channels and "reverse" in self.sounds:
            self.play_loop("reverse", 0.25)
