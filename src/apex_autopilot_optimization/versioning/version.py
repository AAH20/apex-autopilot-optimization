"""Semantic version primitives.

Defines :class:`Version`, an immutable semantic-version value object with
parsing, formatting, comparison, compatibility, and bump operations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_VERSION_RE = re.compile(
    r"^v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?"
    r"(?:\+[0-9A-Za-z.-]+)?$"
)


def _compare_prerelease(left: str, right: str) -> int:
    """Compare two prerelease identifiers per semantic-version rules."""
    left_parts = left.split(".")
    right_parts = right.split(".")
    for a, b in zip(left_parts, right_parts, strict=False):
        a_num = a.isdigit()
        b_num = b.isdigit()
        if a_num and b_num:
            diff = int(a) - int(b)
            if diff != 0:
                return (diff > 0) - (diff < 0)
        elif a_num != b_num:
            # Numeric identifiers always have lower precedence than alphanumeric.
            return -1 if a_num else 1
        elif a != b:
            return (a > b) - (a < b)
    return (len(left_parts) > len(right_parts)) - (len(left_parts) < len(right_parts))


@dataclass(frozen=True)
class Version:
    """An immutable semantic version.

    Attributes:
        major: Major component; bumped on breaking changes.
        minor: Minor component; bumped on backwards-compatible additions.
        patch: Patch component; bumped on backwards-compatible fixes.
        prerelease: Optional prerelease identifier (e.g. ``"rc.1"``).
    """

    major: int
    minor: int
    patch: int
    prerelease: str | None = None

    @classmethod
    def from_string(cls, s: str) -> Version:
        """Parse a version string such as ``"1.2.3-rc.1+build.7"``.

        Raises:
            ValueError: If ``s`` is not a valid ``MAJOR.MINOR.PATCH`` version.
        """
        match = _VERSION_RE.match(s.strip())
        if match is None:
            raise ValueError(f"Invalid version string: {s!r}")
        return cls(
            major=int(match.group("major")),
            minor=int(match.group("minor")),
            patch=int(match.group("patch")),
            prerelease=match.group("prerelease"),
        )

    def to_string(self) -> str:
        """Render the version back to canonical string form."""
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            return f"{base}-{self.prerelease}"
        return base

    def compare(self, other: Version) -> int:
        """Return -1, 0, or 1 ordering ``self`` relative to ``other``.

        Prereleases sort before the corresponding release, per semantic
        versioning.

        Raises:
            TypeError: If ``other`` is not a :class:`Version`.
        """
        if not isinstance(other, Version):
            raise TypeError(f"Cannot compare Version with {type(other).__name__}")
        for a, b in (
            (self.major, other.major),
            (self.minor, other.minor),
            (self.patch, other.patch),
        ):
            if a != b:
                return (a > b) - (a < b)
        if self.prerelease and other.prerelease:
            return _compare_prerelease(self.prerelease, other.prerelease)
        if self.prerelease:
            return -1
        if other.prerelease:
            return 1
        return 0

    def is_compatible(self, other: Version) -> bool:
        """Return whether ``other`` is API-compatible with ``self``.

        Compatibility requires the same major version. For ``0.x`` versions
        (unstable by convention) the minor version must also match.
        """
        if self.major == 0 or other.major == 0:
            return self.major == other.major and self.minor == other.minor
        return self.major == other.major

    def is_prerelease(self) -> bool:
        """Return whether this version carries a prerelease identifier."""
        return bool(self.prerelease)

    def bump_major(self) -> Version:
        """Return a copy with the major component incremented."""
        return Version(self.major + 1, 0, 0)

    def bump_minor(self) -> Version:
        """Return a copy with the minor component incremented."""
        return Version(self.major, self.minor + 1, 0)

    def bump_patch(self) -> Version:
        """Return a copy with the patch component incremented."""
        return Version(self.major, self.minor, self.patch + 1)
