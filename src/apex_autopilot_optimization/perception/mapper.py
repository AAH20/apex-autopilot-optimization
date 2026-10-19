"""ClassMapper: COCO class -> vendor-agnostic WTA target type mapping.

Data-driven mapping table (Section 5 of the perception pipeline spec).
Unknown COCO classes fall back to ``unclassified_target`` without crashing.
``aerial_clutter`` is suppressed unless ``include_clutter=true``.
"""

from __future__ import annotations

from typing import Any

from apex_autopilot_optimization.perception import (
    CLASS_MAP,
    DEFAULT_ENTRY,
    TIER_MIN_CONFIDENCE,
    TargetType,
)
from apex_autopilot_optimization.perception import (
    ClassMapEntry as ClassMapEntryT,
)


class ClassMapper:
    """Maps COCO class names (AAS) to vendor-agnostic WTA target types."""

    def __init__(
        self, class_map: dict[str, ClassMapEntryT] | None = None, include_clutter: bool = False
    ) -> None:
        self._map = dict(class_map) if class_map is not None else dict(CLASS_MAP)
        self.include_clutter = include_clutter

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> ClassMapper:
        include_clutter = bool(config.get("include_clutter", False))
        return cls(include_clutter=include_clutter)

    def map(self, class_name: str) -> ClassMapEntryT:
        """Return the mapping entry for a COCO class name.

        Unknown classes return the default ``unclassified_target`` entry so the
        mapper is total over all non-empty strings.
        """
        key = class_name.strip().lower()
        entry = self._map.get(key)
        if entry is None:
            return DEFAULT_ENTRY
        return entry

    def target_type(self, class_name: str) -> Any:
        return self.map(class_name).target_type

    def priority(self, class_name: str) -> float:
        return self.map(class_name).priority

    def size_class(self, class_name: str) -> Any:
        return self.map(class_name).size_class

    def is_clutter(self, class_name: str) -> bool:
        return self.map(class_name).target_type is TargetType.AERIAL_CLUTTER

    def publishable(self, class_name: str) -> bool:
        """Whether a class may be published to WTA (clutter gated)."""
        return not (self.is_clutter(class_name) and not self.include_clutter)

    def min_confidence(self, class_name: str) -> float:
        return TIER_MIN_CONFIDENCE[self.map(class_name).tier]
