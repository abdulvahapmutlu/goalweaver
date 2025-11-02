import pytest

from gw_code.algos import fib


def test_fib_small():
    assert fib(0) == 0
    assert fib(1) == 1
    assert fib(10) == 55


def test_fib_raises():
    with pytest.raises(ValueError):
        fib(-1)
