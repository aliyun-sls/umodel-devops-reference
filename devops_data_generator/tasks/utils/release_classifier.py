"""Classify a release/tag name into a coarse release type.

Both adapters call ``classify_release_type`` so cross-provider release
records carry comparable ``release_type`` values.

The previous codeup implementation used substring matching
(``'a' in tag_lower``), which classifies ``release-1.0`` as ``alpha``.
This module uses word-boundary regex to avoid that.
"""

import re

# Each entry: (release_type, compiled regex matched against lowercased tag).
# Order matters — first match wins.
_PATTERNS = [
    ("alpha", re.compile(r"(?:^|[-._/])alpha(?:[-._/]|\d|$)")),
    ("beta", re.compile(r"(?:^|[-._/])beta(?:[-._/]|\d|$)")),
    ("release_candidate", re.compile(r"(?:^|[-._/])(?:rc|release[-_]?candidate)(?:[-._/]|\d|$)")),
    ("hotfix", re.compile(r"(?:^|[-._/])(?:hotfix|patch)(?:[-._/]|\d|$)")),
    ("development", re.compile(r"(?:^|[-._/])(?:dev|development|snapshot)(?:[-._/]|\d|$)")),
]

_VERSION_FALLBACK = re.compile(r"(?:^v?\d+|[-._]\d+)")


def classify_release_type(tag_name: str) -> str:
    """Return one of: alpha | beta | release_candidate | hotfix |
    development | release | other.
    """
    if not tag_name:
        return "other"
    tag_lower = tag_name.lower()

    for label, pattern in _PATTERNS:
        if pattern.search(tag_lower):
            return label

    if tag_lower.startswith("v") and len(tag_lower) > 1 and (tag_lower[1].isdigit() or tag_lower[1] == "."):
        return "release"
    if _VERSION_FALLBACK.search(tag_lower):
        return "release"
    return "other"
