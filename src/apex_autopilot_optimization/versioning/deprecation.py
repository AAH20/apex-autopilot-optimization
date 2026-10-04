"""Deprecation policy evaluation.

Models the lifecycle of a deprecated API: the version at which it was
deprecated, the version at which it will be removed, and a human-readable
message. Helper functions classify a queried version against a policy.
"""

from __future__ import annotations

from dataclasses import dataclass

from apex_autopilot_optimization.versioning.version import Version


@dataclass(frozen=True)
class DeprecationPolicy:
    """Lifecycle window for a deprecated API.

    Attributes:
        deprecated_in: Version at which the API became deprecated.
        removal_version: Version at which the API is (or will be) removed.
        message: Guidance shown to callers, typically naming a replacement.
    """

    deprecated_in: Version
    removal_version: Version
    message: str


def is_deprecated(version: Version, policy: DeprecationPolicy) -> bool:
    """Return whether ``version`` falls inside the deprecation window.

    The window is ``[deprecated_in, removal_version)``.
    """
    at_or_after = version.compare(policy.deprecated_in) >= 0
    before_removal = version.compare(policy.removal_version) < 0
    return at_or_after and before_removal


def is_removed(version: Version, policy: DeprecationPolicy) -> bool:
    """Return whether ``version`` is at or past the removal version."""
    return version.compare(policy.removal_version) >= 0


def get_deprecation_warning(version: Version, policy: DeprecationPolicy) -> str | None:
    """Return a warning string if ``version`` is deprecated, else ``None``."""
    if not is_deprecated(version, policy):
        return None
    return (
        f"Deprecated since {policy.deprecated_in.to_string()}; "
        f"scheduled for removal in {policy.removal_version.to_string()}. "
        f"{policy.message}"
    )
