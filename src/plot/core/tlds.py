"""Supported suffixes and reserved names: R-NAME-04..05 (SPEC §6.1, §13.2, §13.3)."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from plot.core.errors import ReservedName
from plot.core.names import is_within, normalize_name, split_registrable

DEFAULT_MIN_NS = 2
MAX_NS = 13
# Always reserved: the sandbox root zone uses a.root-servers.net for its own NS.
ALWAYS_RESERVED = frozenset({"root-servers.net"})


@dataclass(frozen=True)
class SuffixRule:
    min_ns: int = DEFAULT_MIN_NS


@dataclass(frozen=True)
class RegistrableName:
    name: str
    label: str
    suffix: str
    min_ns: int


class NamePolicy:
    """Decides whether a name can be registered in the sandbox."""

    def __init__(self, suffixes: Mapping[str, SuffixRule], reserved: Iterable[str] = ()) -> None:
        self.suffixes = dict(suffixes)
        self.reserved = frozenset(reserved) | ALWAYS_RESERVED

    def is_reserved(self, name: str) -> bool:
        return any(is_within(name, r) for r in self.reserved)

    def min_ns(self, suffix: str) -> int:
        return self.suffixes[suffix].min_ns

    def parse_registrable(self, raw: str) -> RegistrableName:
        """Apply R-NAME-01..05 in order and return the parts of a registrable name."""
        name = normalize_name(raw)
        label, suffix = split_registrable(name, self.suffixes)
        if self.is_reserved(name):
            raise ReservedName(name=name)
        return RegistrableName(name, label, suffix, self.suffixes[suffix].min_ns)


def parse_tlds(data: object) -> dict[str, SuffixRule]:
    """Validate the structure of ``tlds.yml`` (already parsed) and return its suffix rules."""
    if not isinstance(data, dict) or not isinstance(data.get("suffixes"), dict):
        raise ValueError("tlds config must be a mapping with a 'suffixes' mapping")
    rules: dict[str, SuffixRule] = {}
    for raw_suffix, options in data["suffixes"].items():
        suffix = normalize_name(str(raw_suffix))
        if options is None:
            options = {}
        if not isinstance(options, dict) or set(options) - {"min_ns"}:
            raise ValueError(f"suffix {suffix!r}: only 'min_ns' is allowed")
        min_ns = options.get("min_ns", DEFAULT_MIN_NS)
        if type(min_ns) is not int or not 1 <= min_ns <= MAX_NS:
            raise ValueError(f"suffix {suffix!r}: min_ns must be an integer 1..{MAX_NS}")
        if suffix in rules:
            raise ValueError(f"suffix {suffix!r} listed twice")
        rules[suffix] = SuffixRule(min_ns=min_ns)
    if not rules:
        raise ValueError("tlds config lists no suffixes")
    return rules


def parse_passthrough(text: str) -> frozenset[str]:
    """One domain per line; blank lines and ``#`` comments are ignored."""
    names = set()
    for line in text.splitlines():
        entry = line.split("#", 1)[0].strip()
        if entry:
            names.add(normalize_name(entry))
    return frozenset(names)


def load_tlds(path: Path) -> dict[str, SuffixRule]:
    return parse_tlds(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_passthrough(path: Path) -> frozenset[str]:
    return parse_passthrough(path.read_text(encoding="utf-8"))


def load_name_policy(tlds_path: Path, passthrough_path: Path) -> NamePolicy:
    return NamePolicy(load_tlds(tlds_path), load_passthrough(passthrough_path))
