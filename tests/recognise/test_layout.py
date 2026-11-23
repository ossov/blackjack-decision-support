from bjds.recognise.layout import Layout


def test_layout_units_map_to_frame_pixels():
    lay = Layout.load()
    # the layout's (0, 0) sits inside the 16:9 video frame at the stored origin
    x, y = lay.to_frame(0, 0)
    assert round(x) == round(-lay.origin[0] * lay.k) and round(y) == round(-lay.origin[1] * lay.k)
    assert lay.frame == (1920, 1080)


def test_every_seat_has_an_expected_bubble_spot():
    lay = Layout.load()
    assert sorted(lay.bubble_spots()) == [0, 1, 2, 3, 4, 5, 6, 7]   # 0 is the dealer


def test_dealer_bubble_spot_is_where_the_real_table_shows_it():
    # measured on two real-table recordings against the nearby seats 6 and 7:
    # the dealer bubble sits 13 frame pixels higher and 4.5 further left than first traced
    from bjds.recognise.layout import Layout
    x, y = Layout.load().bubble_spots()[0]
    assert abs(x - 604) <= 2 and abs(y - 594) <= 2
