"""Game audio: ambient loops, engine music, crash (paths resolved from project root)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

_ROOT = Path(__file__).resolve().parent.parent


def _sound_path(name: str) -> Path:
    return _ROOT / "sound" / name


class SoundManager:
    def __init__(self) -> None:
        import pygame

        self._pygame = pygame
        self.channels: Dict[str, Any] = {}
        self.sounds: Dict[str, Any] = {}
        for key, rel in (
            ("bg", "background.mp3"),
            ("reverse", "reverselambo.mp3"),
            ("crash", "Hitsound.mp3"),
            # One-shot cue fired the moment the player lets off the gas.
            ("release", "slowreal.mp3"),
            # One-shot whoosh when a nitro boost kicks in.
            ("nitro", "nitro.mp3"),
            # One-shot tire skid played when the player steps on a banana peel.
            ("slip", "driff.mp3"),
        ):
            path = _sound_path(rel)
            if not path.is_file():
                continue
            try:
                self.sounds[key] = pygame.mixer.Sound(str(path))
            except Exception:
                continue

        self.music_paths: Dict[str, str] = {}
        for key, rel in (("lambo", "lamboreal02.mp3"), ("slow", "slow03.mp3")):
            p = _sound_path(rel)
            if p.is_file():
                self.music_paths[key] = str(p)

        self.current_music: Optional[str] = None

    def play_loop(self, name: str, volume: float) -> None:
        s = self.sounds.get(name)
        if s is None:
            return
        ch = s.play(-1)
        ch.set_volume(volume)
        self.channels[name] = ch

    def play_once(self, name: str) -> None:
        s = self.sounds.get(name)
        if s is not None:
            s.play()

    def music(self, name: str, volume: float) -> None:
        import pygame

        if self.current_music == name:
            return
        path = self.music_paths.get(name)
        if path is None:
            return
        pygame.mixer.music.stop()
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.play(-1)
            pygame.mixer.music.set_volume(volume)
            self.current_music = name
        except Exception:
            self.current_music = None

    def stop_music(self) -> None:
        import pygame

        pygame.mixer.music.stop()
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

    def silence_gameplay(self) -> None:
        """Leave only the background music loop; kill everything else.

        Stops tracked loops (engine reverse), the track-music channel, and
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
