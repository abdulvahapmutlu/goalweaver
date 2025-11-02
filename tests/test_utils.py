import pytest

from gw_code.utils import slugify


def test_slugify_basic():
    assert slugify("Hello World") == "hello-world"


@pytest.mark.parametrize(
    "inp,exp",
    [
        ("Türkçe Karakter", "turkce-karakter"),
        (" multiple   spaces ", "multiple-spaces"),
        ("Café-au-lait", "cafe-au-lait"),
    ],
)
def test_slugify_variants(inp, exp):
    assert slugify(inp) == exp
