"""Capture Path event types for speech entering the Voice Keyboard Engine."""

from dataclasses import dataclass
from typing import Literal


CaptureMode = Literal["dictation", "instruction_edit", "instruction"]


@dataclass(frozen=True)
class UtteranceEvent:
    pcm: bytes
    mode: CaptureMode = "dictation"
    polish: bool = False

    @classmethod
    def dictation(cls, pcm: bytes, polish: bool = False) -> "UtteranceEvent":
        return cls(pcm=pcm, mode="dictation", polish=polish)

    @classmethod
    def instruction_edit(cls, pcm: bytes) -> "UtteranceEvent":
        return cls(pcm=pcm, mode="instruction_edit")

    @classmethod
    def instruction(cls, pcm: bytes) -> "UtteranceEvent":
        return cls(pcm=pcm, mode="instruction")
