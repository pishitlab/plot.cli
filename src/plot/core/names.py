"""Domain/host name rules R-NAME-01..03 (SPEC §6.1)."""

import re
from collections.abc import Collection

from plot.core.errors import InvalidName, NotRegistrable, TldNotSupported

MAX_NAME_LENGTH = 253
_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def normalize_name(raw: str) -> str:
    """Return the canonical form of ``raw`` (R-NAME-01) after checking its syntax (R-NAME-02)."""
    name = raw.strip()
    # Check ASCII before lowercasing: some non-ASCII letters lowercase into ASCII.
    if not name.isascii():
        raise InvalidName("name must be ASCII (use xn-- for IDN)", name=raw)
    name = name.lower()
    if name.endswith("."):
        name = name[:-1]
    if not name:
        raise InvalidName("name is empty", name=raw)
    if len(name) > MAX_NAME_LENGTH:
        raise InvalidName(f"name longer than {MAX_NAME_LENGTH} characters", name=raw)
    for label in name.split("."):
        if not _LABEL_RE.match(label):
            raise InvalidName(f"invalid label {label!r}", name=raw)
    return name


def is_within(name: str, parent: str) -> bool:
    """True when ``name`` equals ``parent`` or is below it. Both must be normalized."""
    return name == parent or name.endswith("." + parent)


def name_and_ancestors(name: str) -> list[str]:
    """``name`` followed by each parent name, longest first (``a.b.c`` -> a.b.c, b.c, c)."""
    labels = name.split(".")
    return [".".join(labels[i:]) for i in range(len(labels))]


def split_registrable(name: str, suffixes: Collection[str]) -> tuple[str, str]:
    """Split a normalized ``name`` into (label, suffix) using the longest known suffix.

    Raises ``TldNotSupported`` when no suffix matches and ``NotRegistrable`` when the
    name is not exactly one label plus that suffix (R-NAME-03).
    """
    for candidate in name_and_ancestors(name):
        if candidate in suffixes:
            if candidate == name:
                raise NotRegistrable("name is a public suffix", name=name, suffix=candidate)
            label = name[: -len(candidate) - 1]
            if "." in label:
                raise NotRegistrable(
                    "only one label below the suffix can be registered",
                    name=name,
                    suffix=candidate,
                )
            return label, candidate
    raise TldNotSupported(name=name)
