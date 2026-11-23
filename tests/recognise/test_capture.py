"""Turning a screen capture of the video area into the 16:9 frame that Recognition reads."""
import numpy as np

from bjds.recognise.capture import stage_to_frame, frame_to_stage


def test_a_stage_narrower_than_16_9_is_the_middle_of_the_frame():
    # the page fills the height and crops the sides, like the live page
    stage = np.zeros((965, 1482, 3), np.uint8)
    stage[480:485, 738:744] = 255                 # a dot in the middle of the stage
    frame = stage_to_frame(stage)
    assert frame.shape == (1080, 1920, 3)
    ys, xs = np.nonzero(frame[..., 0])
    assert abs(xs.mean() - 960) < 3 and abs(ys.mean() - 540) < 3


def test_frame_points_map_back_onto_the_stage():
    x, y = frame_to_stage(960, 540, stage_size=(1482, 965))
    assert abs(x - 741) < 1 and abs(y - 482.5) < 1
    x0, _ = frame_to_stage(0, 0, stage_size=(1482, 965))
    assert x0 < 0                                  # the frame's left edge is cropped off screen
