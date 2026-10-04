"""Digital twin core class."""

from __future__ import annotations

import time
import uuid
from typing import Any

from apex_autopilot_optimization.twin.asset import TwinAsset


class DigitalTwin:
    """Manages a collection of digital twin assets."""

    def __init__(self) -> None:
        self._assets: dict[str, TwinAsset] = {}

    def _find_asset(self, key: str) -> TwinAsset | None:
        """Find an asset by ID first, then by type."""
        asset = self._assets.get(key)
        if asset is not None:
            return asset
        for a in self._assets.values():
            if a.type == key:
                return a
        return None

    def create_asset(self, asset_type: str, config: dict[str, Any]) -> TwinAsset:
        """Create a new twin asset and return it."""
        asset_id = uuid.uuid4().hex[:12]
        now = time.time()
        asset = TwinAsset(
            id=asset_id,
            type=asset_type,
            state=dict(config),
            created_at=now,
            updated_at=now,
        )
        self._assets[asset_id] = asset
        return asset

    def get_asset(self, asset_id: str) -> TwinAsset | None:
        """Retrieve an asset by ID, or None if not found."""
        return self._assets.get(asset_id)

    def update_asset(self, asset_id: str, state: dict[str, Any]) -> TwinAsset | None:
        """Update an asset's state and return it, or None if not found."""
        asset = self._assets.get(asset_id)
        if asset is None:
            return None
        asset.state = dict(state)
        asset.updated_at = time.time()
        return asset

    def delete_asset(self, asset_id: str) -> bool:
        """Delete an asset by ID. Returns True if deleted, False if not found."""
        if asset_id in self._assets:
            del self._assets[asset_id]
            return True
        return False

    def list_assets(self) -> list[TwinAsset]:
        """Return a list of all twin assets."""
        return list(self._assets.values())

    def get_asset_state(self, asset_id: str) -> dict[str, Any] | None:
        """Get the state dict of an asset, or None if not found."""
        asset = self._find_asset(asset_id)
        if asset is None:
            return None
        return dict(asset.state)

    def set_asset_state(self, asset_id: str, state: dict[str, Any]) -> bool:
        """Set the state of an asset. Returns True on success, False if not found."""
        asset = self._find_asset(asset_id)
        if asset is None:
            return False
        asset.state = dict(state)
        asset.updated_at = time.time()
        return True
