import pytest

from plot.core.errors import InvalidName, NotRegistrable, TldNotSupported
from plot.core.names import is_within, name_and_ancestors, normalize_name, split_registrable

SUFFIXES = frozenset({"com", "net", "th", "co.th"})


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("shop.com", "shop.com"),
        ("  Shop.COM.  ", "shop.com"),
        ("NS1.MyHost.NET.", "ns1.myhost.net"),
        ("\tx.th\n", "x.th"),
    ],
)
def test_R_NAME_01_normalizes_trim_lowercase_trailing_dot(raw: str, expected: str) -> None:
    assert normalize_name(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", ".", " . "])
def test_R_NAME_01_rejects_empty(raw: str) -> None:
    with pytest.raises(InvalidName):
        normalize_name(raw)


def test_R_NAME_01_strips_only_one_trailing_dot() -> None:
    with pytest.raises(InvalidName):
        normalize_name("shop.com..")


@pytest.mark.parametrize(
    "raw",
    [
        "sh_op.com",  # underscore
        "-shop.com",  # leading hyphen
        "shop-.com",  # trailing hyphen
        "sh op.com",  # space inside
        "shop..com",  # empty label
        ".shop.com",  # leading empty label
        "a" * 64 + ".com",  # label > 63
        "ร้าน.com",  # non-ASCII (IDN must be given as xn--)
        chr(0x212A) + "elvin.com",  # KELVIN SIGN lowercases to ASCII "k"; must not slip through
        "shop.com/x",
    ],
)
def test_R_NAME_02_rejects_bad_labels(raw: str) -> None:
    with pytest.raises(InvalidName):
        normalize_name(raw)


def test_R_NAME_02_accepts_boundary_labels() -> None:
    assert normalize_name("a" * 63 + ".com") == "a" * 63 + ".com"
    assert normalize_name("a-1.com") == "a-1.com"
    assert normalize_name("xn--12c1fe0br.com") == "xn--12c1fe0br.com"
    assert normalize_name("9.com") == "9.com"


def test_R_NAME_02_total_length_limit_253() -> None:
    label = "a" * 63
    name_253 = ".".join([label, label, label, "a" * 61])
    assert len(name_253) == 253
    assert normalize_name(name_253) == name_253
    with pytest.raises(InvalidName):
        normalize_name(name_253 + "a")
    # trailing dot does not count towards the limit
    assert normalize_name(name_253 + ".") == name_253


@pytest.mark.parametrize(
    ("name", "label", "suffix"),
    [
        ("shop.com", "shop", "com"),
        ("shop.co.th", "shop", "co.th"),  # longest suffix wins over "th"
        ("shop.th", "shop", "th"),
    ],
)
def test_R_NAME_03_registrable_is_one_label_plus_longest_suffix(
    name: str, label: str, suffix: str
) -> None:
    assert split_registrable(name, SUFFIXES) == (label, suffix)


@pytest.mark.parametrize("name", ["www.shop.com", "a.b.th", "x.shop.co.th", "com", "co.th"])
def test_R_NAME_03_rejects_subdomains_and_bare_suffixes(name: str) -> None:
    with pytest.raises(NotRegistrable):
        split_registrable(name, SUFFIXES)


def test_split_registrable_unknown_suffix_is_tld_not_supported() -> None:
    with pytest.raises(TldNotSupported):
        split_registrable("shop.xyz", SUFFIXES)


def test_is_within_matches_self_and_descendants_only() -> None:
    assert is_within("shop.com", "shop.com")
    assert is_within("ns1.shop.com", "shop.com")
    assert not is_within("myshop.com", "shop.com")
    assert not is_within("shop.com", "ns1.shop.com")


def test_name_and_ancestors_longest_first() -> None:
    assert name_and_ancestors("ns1.shop.co.th") == [
        "ns1.shop.co.th",
        "shop.co.th",
        "co.th",
        "th",
    ]
