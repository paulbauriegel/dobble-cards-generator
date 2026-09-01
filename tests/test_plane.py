import pytest

from dobble.plane import deck_size, dobble, order_for, verify


@pytest.mark.parametrize("n", [2, 3, 5, 7])
def test_dobble_is_a_valid_deck(n):
    cards = dobble(n)
    assert len(cards) == deck_size(n)
    verify(cards, n)


@pytest.mark.parametrize("count,n", [(7, 2), (13, 3), (31, 5), (57, 7), (133, 11)])
def test_order_for_valid_counts(count, n):
    assert order_for(count) == n


@pytest.mark.parametrize("count", [1, 3, 20, 21, 40, 58, 73])
def test_order_for_rejects_invalid_counts(count):
    # 21 = 4^2 + 4 + 1 and 73 = 8^2 + 8 + 1 are prime powers, which this construction does not support
    with pytest.raises(ValueError):
        order_for(count)


def test_verify_detects_broken_deck():
    cards = dobble(3)
    cards[0][0] = cards[0][1]
    with pytest.raises(AssertionError):
        verify(cards, 3)
