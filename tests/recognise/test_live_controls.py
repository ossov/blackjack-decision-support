from bjds.recognise.live import inside, reset_button

WIDTH, SCALE = 1690 * 2, (910 * 2) / 1080


def test_reset_button_sits_in_the_top_bar_on_the_right():
    x0, y0, x1, y1 = reset_button(WIDTH, SCALE)
    bar = int(40 * SCALE * 2)
    assert 0 <= y0 < y1 <= bar
    assert WIDTH / 2 < x0 < x1 <= WIDTH


def test_a_click_inside_the_reset_button_hits_it_and_one_outside_does_not():
    rect = reset_button(WIDTH, SCALE)
    x0, y0, x1, y1 = rect
    assert inside(rect, (x0 + x1) // 2, (y0 + y1) // 2)
    assert not inside(rect, x0 - 5, (y0 + y1) // 2)
    assert not inside(rect, (x0 + x1) // 2, y1 + 5)


def test_reset_button_does_not_cover_the_longest_status_text():
    import cv2
    longest = "14 bubbles  |  145 ms  |  bubbles match sim 99.9% (12345 reads)  |  count mistakes 10"
    (w, _), _ = cv2.getTextSize(longest, cv2.FONT_HERSHEY_SIMPLEX, 0.7 * SCALE * 2, max(1, int(2 * SCALE)))
    x0, *_ = reset_button(WIDTH, SCALE)
    assert 12 + w < x0
