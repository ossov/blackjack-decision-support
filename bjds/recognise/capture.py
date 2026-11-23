"""Screen capture of the video area, turned into the 16:9 frame Recognition reads.

Both the simulator and the live page show the whole 16:9 video picture fitted to the height of
their video area, with the sides cropped. So a capture of that area is the middle of the frame:
it is scaled to 1080 pixels high and placed in the centre of a 1920x1080 frame.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

FRAME_W, FRAME_H = 1920, 1080
REGION_FILE = Path(__file__).resolve().parents[2] / "config" / "capture.json"


def _fit(stage_w: int, stage_h: int) -> tuple[float, float]:
    """Scale from frame to stage pixels, and the frame's x offset on the stage."""
    scale = stage_h / FRAME_H
    return scale, (stage_w - FRAME_W * scale) / 2


def stage_to_frame(stage: np.ndarray) -> np.ndarray:
    h, w = stage.shape[:2]
    scale, off = _fit(w, h)
    visible_w = int(round(w / scale))
    resized = cv2.resize(stage, (visible_w, FRAME_H), interpolation=cv2.INTER_AREA if scale > 1 else cv2.INTER_LINEAR)
    frame = np.zeros((FRAME_H, FRAME_W, 3), np.uint8)
    x0 = int(round(-off / scale))
    src0, dst0 = max(0, -x0), max(0, x0)
    width = min(visible_w - src0, FRAME_W - dst0)
    frame[:, dst0:dst0 + width] = resized[:, src0:src0 + width]
    return frame


def frame_to_stage(x: float, y: float, stage_size: tuple[int, int]) -> tuple[float, float]:
    scale, off = _fit(*stage_size)
    return x * scale + off, y * scale


def save_region(region: dict) -> None:
    REGION_FILE.write_text(json.dumps(region, indent=2) + "\n")


def load_region() -> dict | None:
    return json.loads(REGION_FILE.read_text()) if REGION_FILE.exists() else None


class ScreenGrabber:
    """Grabs one screen region (in screen points) with mss."""

    def __init__(self, region: dict):
        import mss
        self.sct = mss.mss()
        self.region = {k: int(region[k]) for k in ("left", "top", "width", "height")}

    def grab(self) -> np.ndarray:
        shot = np.asarray(self.sct.grab(self.region))      # BGRA, at the screen's real resolution
        return cv2.cvtColor(shot, cv2.COLOR_BGRA2BGR)
