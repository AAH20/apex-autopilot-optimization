"""Formal verification configuration."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FormalConfig:
    """Configuration for the formal verification package."""

    enabled: bool = False
    verification_level: str = "basic"
    auto_verify: bool = False
    report_format: str = "text"
