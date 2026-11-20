from bjds.engine import demo


def test_simulated_shoes_never_give_a_wrong_card(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert demo.play(300, seed=5, verbose=False, pictures=False)["wrong"] == 0


def test_simulated_shoes_with_card_pictures_have_no_uncertain_cards(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = demo.play(300, seed=5, verbose=False, pictures=True)
    assert r == {"wrong": 0, "uncertain_rounds": 0, "uncertain": 0}
