"""Backward-compatibility shim.

The canonical implementations now live in :mod:`property` and :mod:`case`;
this module re-exports them for existing imports.
"""

from apex_autopilot_optimization.formal.case import SafetyCase
from apex_autopilot_optimization.formal.property import (
    SafetyProperty,
    SafetySeverity,
    get_property_status,
    verify_property,
)

__all__ = [
    "SafetyCase",
    "SafetyProperty",
    "SafetySeverity",
    "get_property_status",
    "verify_property",
]
