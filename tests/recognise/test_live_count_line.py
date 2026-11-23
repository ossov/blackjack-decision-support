from types import SimpleNamespace

import cv2

from bjds.recognise.live import count_lines

RESULT = SimpleNamespace(running_count=-13, true_count=-1.85, uncertain_cards=2)
TRUTH = {"running_count": -13, "true_count": -1.85, "cards_seen": 215}


def test_count_lines_show_the_cards_the_detector_has_seen():
    lines = count_lines(RESULT, cards_seen=214)
    assert len(lines) == 1
    assert "DETECTED" in lines[0] and "cards seen 214" in lines[0]


def test_the_simulators_cards_seen_go_on_their_own_line():
    detected, simulator = count_lines(RESULT, cards_seen=214, truth=TRUTH)
    assert "cards seen 214" in detected
    assert simulator.startswith("SIMULATOR") and "cards seen 215" in simulator


def test_each_count_line_fits_across_the_window():
    width, height = 1690 * 2, 910 * 2          # the saved capture area on a Retina screen
    scale = height / 1080
    for line in count_lines(RESULT, cards_seen=214, truth=TRUTH):
        (w, _), _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, 0.7 * scale * 2, max(1, int(2 * scale)))
        assert w < width
