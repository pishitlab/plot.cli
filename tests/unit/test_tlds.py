from pathlib import Path

import pytest

from plot.core.errors import InvalidName, NotRegistrable, ReservedName, TldNotSupported
from plot.core.tlds import (
    NamePolicy,
    SuffixRule,
    load_name_policy,
    parse_passthrough,
    parse_tlds,
)

CONFIG = Path(__file__).resolve().parents[2] / "config"


@pytest.fixture(scope="module")
def default_policy() -> NamePolicy:
    return load_name_policy(CONFIG / "tlds.yml", CONFIG / "passthrough.txt")


def test_default_config_matches_spec(default_policy: NamePolicy) -> None:
    assert set(default_policy.suffixes) == {
        "com",
        "net",
        "org",
        "info",
        "io",
        "dev",
        "th",
        "co.th",
        "in.th",
        "or.th",
        "ac.th",
        "go.th",
    }
    assert all(rule.min_ns == 2 for rule in default_policy.suffixes.values())
    assert "github.com" in default_policy.reserved
    assert len(default_policy.reserved) == 11  # 10 passthrough + root-servers.net


def test_parse_registrable_returns_parts(default_policy: NamePolicy) -> None:
    parsed = default_policy.parse_registrable(" Shop.CO.TH. ")
    assert (parsed.name, parsed.label, parsed.suffix, parsed.min_ns) == (
        "shop.co.th",
        "shop",
        "co.th",
        2,
    )


@pytest.mark.parametrize("raw", ["shop.xyz", "shop.uk", "shop.local"])
def test_R_NAME_04_suffix_must_be_in_tlds_yml(default_policy: NamePolicy, raw: str) -> None:
    with pytest.raises(TldNotSupported):
        default_policy.parse_registrable(raw)


def test_R_NAME_04_suffix_list_comes_from_config() -> None:
    policy = NamePolicy(parse_tlds({"suffixes": {"test": {"min_ns": 1}}}))
    assert policy.parse_registrable("a.test").min_ns == 1
    with pytest.raises(TldNotSupported):
        policy.parse_registrable("a.com")


@pytest.mark.parametrize("raw", ["github.com", "GitHub.com.", "pypi.org", "root-servers.net"])
def test_R_NAME_05_passthrough_and_root_servers_are_reserved(
    default_policy: NamePolicy, raw: str
) -> None:
    with pytest.raises(ReservedName):
        default_policy.parse_registrable(raw)


def test_R_NAME_05_names_below_reserved_domain_are_reserved() -> None:
    policy = NamePolicy({"com": SuffixRule(), "co.th": SuffixRule()}, {"example.co.th"})
    with pytest.raises(ReservedName):
        policy.parse_registrable("example.co.th")
    assert policy.is_reserved("www.example.co.th")
    assert not policy.is_reserved("myexample.co.th")
    assert policy.parse_registrable("github-mirror.com").name == "github-mirror.com"


def test_rule_order_invalid_then_suffix_then_registrable(default_policy: NamePolicy) -> None:
    with pytest.raises(InvalidName):
        default_policy.parse_registrable("git_hub.com")
    with pytest.raises(NotRegistrable):
        default_policy.parse_registrable("www.github.com")


def test_parse_tlds_defaults_min_ns() -> None:
    assert parse_tlds({"suffixes": {"com": None, "NET.": {}}}) == {
        "com": SuffixRule(2),
        "net": SuffixRule(2),
    }


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        {"suffixes": []},
        {"suffixes": {}},
        {"suffixes": {"com": {"min_ns": 0}}},
        {"suffixes": {"com": {"min_ns": 14}}},
        {"suffixes": {"com": {"min_ns": "2"}}},
        {"suffixes": {"com": {"min_ns": True}}},
        {"suffixes": {"com": {"max_ns": 3}}},
        {"suffixes": {"com": 2}},
        {"suffixes": {"com": {}, "COM": {}}},
    ],
)
def test_parse_tlds_rejects_bad_config(data: object) -> None:
    with pytest.raises(ValueError):
        parse_tlds(data)


def test_parse_passthrough_ignores_comments_and_blank_lines() -> None:
    text = "# header\n\nGitHub.com.\n  pypi.org  # python\n"
    assert parse_passthrough(text) == frozenset({"github.com", "pypi.org"})


def test_parse_passthrough_rejects_invalid_entries() -> None:
    with pytest.raises(InvalidName):
        parse_passthrough("bad_name.com\n")
