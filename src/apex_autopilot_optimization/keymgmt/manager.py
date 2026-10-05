"""Key manager for encryption key lifecycle."""

from __future__ import annotations

import os
import time
import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from apex_autopilot_optimization.keymgmt.version import KeyStatus, KeyVersion

_NONCE_SIZE = 12
_KEY_SIZE = 32


class KeyManager:
    """Manages encryption keys: generation, rotation, retirement, encrypt/decrypt."""

    def __init__(self) -> None:
        self._keys: dict[str, KeyVersion] = {}
        self._current_key_id: str | None = None

    def generate_key(self) -> KeyVersion:
        """Generate a new active key.

        Returns:
            The newly created KeyVersion.
        """
        key_id = uuid.uuid4().hex
        key_data = os.urandom(_KEY_SIZE)
        key = KeyVersion(
            key_id=key_id,
            created_at=time.time(),
            expires_at=None,
            status=KeyStatus.ACTIVE,
            key_data=key_data,
        )
        self._keys[key_id] = key
        self._current_key_id = key_id
        return key

    def rotate_key(self) -> KeyVersion:
        """Rotate to a new key, retiring the current one.

        Returns:
            The newly created KeyVersion.
        """
        old_key_id = self._current_key_id
        new_key = self.generate_key()
        if old_key_id is not None and old_key_id != new_key.key_id:
            old_key = self._keys[old_key_id]
            old_key.status = KeyStatus.RETIRED
            old_key.expires_at = time.time()
        return new_key

    def get_key(self, key_id: str) -> KeyVersion | None:
        """Retrieve a key by its ID.

        Args:
            key_id: The key identifier.

        Returns:
            The KeyVersion if found, None otherwise.
        """
        return self._keys.get(key_id)

    def get_current_key(self) -> KeyVersion | None:
        """Get the current active key.

        Returns:
            The current KeyVersion, or None if no key has been generated.
        """
        if self._current_key_id is None:
            return None
        return self._keys.get(self._current_key_id)

    def get_all_keys(self) -> list[KeyVersion]:
        """Get all managed keys.

        Returns:
            List of all KeyVersion objects.
        """
        return list(self._keys.values())

    def retire_key(self, key_id: str, grace_period_days: int) -> None:
        """Retire a key with a grace period before expiry.

        Args:
            key_id: The key identifier to retire.
            grace_period_days: Number of days before the key expires.

        Raises:
            KeyError: If the key_id is not found.
        """
        if key_id not in self._keys:
            raise KeyError(f"Key not found: {key_id}")
        key = self._keys[key_id]
        key.status = KeyStatus.RETIRED
        key.expires_at = time.time() + grace_period_days * 86400.0

    def encrypt(self, plaintext: bytes, key_id: str | None = None) -> bytes:
        """Encrypt plaintext using the specified or current key.

        Args:
            plaintext: The data to encrypt.
            key_id: The key identifier to use. If None, uses the current key.

        Returns:
            The ciphertext (nonce + ciphertext + tag).

        Raises:
            ValueError: If no key is available for encryption.
        """
        if key_id is None:
            key_id = self._current_key_id
        if key_id is None:
            raise ValueError("No key available for encryption")
        key = self._keys[key_id]
        nonce = os.urandom(_NONCE_SIZE)
        aesgcm = AESGCM(key.key_data)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        return nonce + ciphertext

    def decrypt(self, ciphertext: bytes) -> bytes:
        """Decrypt ciphertext and return the plaintext.

        The first 12 bytes are the nonce, the rest is the AES-GCM ciphertext+tag.
        The key_id is not stored in the ciphertext; we try the current key first,
        then all keys.

        Args:
            ciphertext: The data to decrypt.

        Returns:
            The decrypted plaintext.

        Raises:
            ValueError: If decryption fails (tampered ciphertext or wrong key).
            KeyError: If no suitable key is found.
        """
        if len(ciphertext) < _NONCE_SIZE:
            raise ValueError("Ciphertext too short")
        nonce = ciphertext[:_NONCE_SIZE]
        ct = ciphertext[_NONCE_SIZE:]

        # Try current key first, then all keys
        keys_to_try: list[KeyVersion] = []
        if self._current_key_id is not None:
            current = self._keys.get(self._current_key_id)
            if current is not None:
                keys_to_try.append(current)
        keys_to_try.extend(
            k for k in self._keys.values() if k.key_id != self._current_key_id
        )

        if not keys_to_try:
            raise KeyError("No keys available for decryption")

        last_error: Exception | None = None
        for key in keys_to_try:
            try:
                aesgcm = AESGCM(key.key_data)
                return aesgcm.decrypt(nonce, ct, None)
            except Exception as exc:
                last_error = exc
                continue

        if last_error is not None:
            raise ValueError("Decryption failed") from last_error
        raise ValueError("Decryption failed")

    def get_key_count(self) -> int:
        """Get the total number of managed keys.

        Returns:
            The number of keys.
        """
        return len(self._keys)
