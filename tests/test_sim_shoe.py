from sim.cards import Card, Shoe, hilo


def test_same_seed_gives_same_shoe():
    assert Shoe(seed=7).cards == Shoe(seed=7).cards


def test_different_seeds_give_different_shoes():
    assert Shoe(seed=1).cards != Shoe(seed=2).cards


def test_eight_deck_shoe_holds_416_cards():
    assert len(Shoe(seed=1).cards) == 416


def test_each_rank_appears_32_times():
    ranks = [c.rank for c in Shoe(seed=3).cards]
    for rank in ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]:
        assert ranks.count(rank) == 32


def test_full_shoe_counts_back_to_zero():
    assert sum(hilo(c) for c in Shoe(seed=5).cards) == 0


def test_hilo_values():
    assert hilo(Card("2", "S")) == 1
    assert hilo(Card("6", "H")) == 1
    assert hilo(Card("7", "D")) == 0
    assert hilo(Card("9", "C")) == 0
    assert hilo(Card("K", "S")) == -1
    assert hilo(Card("A", "H")) == -1


def test_cut_card_sits_at_half_the_shoe_by_default():
    assert Shoe(seed=1).cut_index == 208


def test_cut_card_comes_out_when_dealing_reaches_it():
    shoe = Shoe(seed=1, penetration=0.5)
    for _ in range(207):
        shoe.draw()
    assert not shoe.cut_card_out
    shoe.draw()
    assert shoe.cut_card_out


def test_stacked_shoe_deals_in_the_given_order():
    shoe = Shoe.stacked(["A", "K", "5"])
    assert [shoe.draw().rank for _ in range(3)] == ["A", "K", "5"]
