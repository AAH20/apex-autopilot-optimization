"""Tests for the keymgmt (key management & secret rotation) package."""

from __future__ import annotations

import time

import pytest

from apex_autopilot_optimization.keymgmt import (
    KeyManager,
    KeyRotationConfig,
    KeyVersion,
    SecretRotationPolicy,
    SecretStore,
)
from apex_autopilot_optimization.keymgmt.rotation import (
    get_next_rotation_date,
    should_rotate,
)
from apex_autopilot_optimization.keymgmt.store import InMemorySecretStore
from apex_autopilot_optimization.keymgmt.version import KeyStatus

DAY = 86400.0


# ── Key generation ──────────────────────────────────────────────────────────


class TestKeyGeneration:
    def test_generate_key_returns_key_version(self):
        mgr = KeyManager()
        assert isinstance(mgr.generate_key(), KeyVersion)

    def test_generate_key_status_is_active(self):
        mgr = KeyManager()
        assert mgr.generate_key().status == KeyStatus.ACTIVE

    def test_generate_key_ids_are_unique(self):
        mgr = KeyManager()
        assert mgr.generate_key().key_id != mgr.generate_key().key_id

    def test_generate_key_data_is_unique(self):
        mgr = KeyManager()
        assert mgr.generate_key().key_data != mgr.generate_key().key_data

    def test_generate_key_produces_32_byte_key(self):
        mgr = KeyManager()
        assert len(mgr.generate_key().key_data) == 32

    def test_generate_key_sets_created_at(self):
        mgr = KeyManager()
        before = time.time()
        key = mgr.generate_key()
        after = time.time()
        assert before <= key.created_at <= after

    def test_generate_key_expires_at_is_none(self):
        mgr = KeyManager()
        assert mgr.generate_key().expires_at is None


# ── Key rotation ────────────────────────────────────────────────────────────


class TestKeyRotation:
    def test_rotate_key_creates_new_active_key(self):
        mgr = KeyManager()
        new_key = mgr.rotate_key()
        assert new_key.status == KeyStatus.ACTIVE
        assert mgr.get_current_key() is not None
        assert mgr.get_current_key().key_id == new_key.key_id

    def test_rotate_key_retires_previous_key(self):
        mgr = KeyManager()
        old_key = mgr.generate_key()
        mgr.rotate_key()
        assert mgr.get_key(old_key.key_id).status == KeyStatus.RETIRED

    def test_rotate_key_sets_expiry_on_retired_key(self):
        mgr = KeyManager()
        old_key = mgr.generate_key()
        mgr.rotate_key()
        assert mgr.get_key(old_key.key_id).expires_at is not None


# ── Key retrieval ───────────────────────────────────────────────────────────


class TestKeyRetrieval:
    def test_get_key_returns_existing_key(self):
        mgr = KeyManager()
        key = mgr.generate_key()
        fetched = mgr.get_key(key.key_id)
        assert fetched is not None
        assert fetched.key_id == key.key_id
        assert fetched.key_data == key.key_data

    def test_get_key_returns_none_for_missing_key(self):
        mgr = KeyManager()
        assert mgr.get_key("no-such-key") is None


# ── Current key ─────────────────────────────────────────────────────────────


class TestCurrentKey:
    def test_get_current_key_returns_none_initially(self):
        mgr = KeyManager()
        assert mgr.get_current_key() is None

    def test_get_current_key_returns_latest_generated_key(self):
        mgr = KeyManager()
        first = mgr.generate_key()
        second = mgr.generate_key()
        current = mgr.get_current_key()
        assert current is not None
        assert current.key_id == second.key_id
        assert current.key_id != first.key_id


# ── All keys ────────────────────────────────────────────────────────────────


class TestAllKeys:
    def test_get_all_keys_empty_initially(self):
        mgr = KeyManager()
        assert mgr.get_all_keys() == []

    def test_get_all_keys_returns_all_generated_keys(self):
        mgr = KeyManager()
        keys = [mgr.generate_key() for _ in range(3)]
        all_keys = mgr.get_all_keys()
        assert len(all_keys) == 3
        assert {k.key_id for k in all_keys} == {k.key_id for k in keys}


# ── Key retirement ─────────────────────────────────────────────────────────


class TestKeyRetirement:
    def test_retire_key_marks_key_retired(self):
        mgr = KeyManager()
        key = mgr.generate_key()
        mgr.retire_key(key.key_id, 7)
        assert mgr.get_key(key.key_id).status == KeyStatus.RETIRED

    def test_retire_key_sets_expiry_with_grace_period(self):
        mgr = KeyManager()
        key = mgr.generate_key()
        before = time.time()
        mgr.retire_key(key.key_id, 7)
        after = time.time()
        expires_at = mgr.get_key(key.key_id).expires_at
        assert expires_at is not None
        assert before + 7 * DAY <= expires_at <= after + 7 * DAY

    def test_retire_key_unknown_key_raises(self):
        mgr = KeyManager()
        with pytest.raises(KeyError):
            mgr.retire_key("no-such-key", 7)


# ── Encrypt / decrypt ──────────────────────────────────────────────────────


class TestEncryptDecrypt:
    def test_encrypt_decrypt_roundtrip(self):
        mgr = KeyManager()
        mgr.generate_key()
        ciphertext = mgr.encrypt(b"hello world")
        assert mgr.decrypt(ciphertext) == b"hello world"

    def test_encrypt_with_explicit_key_id(self):
        mgr = KeyManager()
        key = mgr.generate_key()
        ciphertext = mgr.encrypt(b"secret data", key.key_id)
        assert mgr.decrypt(ciphertext) == b"secret data"

    def test_encrypt_same_plaintext_differs_each_time(self):
        mgr = KeyManager()
        key = mgr.generate_key()
        first = mgr.encrypt(b"same", key.key_id)
        second = mgr.encrypt(b"same", key.key_id)
        assert first != second

    def test_decrypt_tampered_ciphertext_raises(self):
        mgr = KeyManager()
        key = mgr.generate_key()
        ciphertext = bytearray(mgr.encrypt(b"payload", key.key_id))
        ciphertext[len(ciphertext) // 2] ^= 0xFF
        with pytest.raises(ValueError):
            mgr.decrypt(bytes(ciphertext))

    def test_decrypt_with_unknown_key_raises(self):
        mgr1 = KeyManager()
        mgr1.generate_key()
        ciphertext = mgr1.encrypt(b"payload")
        mgr2 = KeyManager()
        with pytest.raises(KeyError):
            mgr2.decrypt(ciphertext)


# ── Key count ───────────────────────────────────────────────────────────────


class TestKeyCount:
    def test_get_key_count_empty(self):
        mgr = KeyManager()
        assert mgr.get_key_count() == 0

    def test_get_key_count_increments(self):
        mgr = KeyManager()
        mgr.generate_key()
        assert mgr.get_key_count() == 1
        mgr.generate_key()
        assert mgr.get_key_count() == 2


# ── KeyRotationConfig ───────────────────────────────────────────────────────


class TestKeyRotationConfig:
    def test_key_rotation_config_defaults(self):
        config = KeyRotationConfig()
        assert config.rotation_interval_days == 30
        assert config.grace_period_days == 7
        assert config.max_active_keys == 5
        assert config.auto_rotate is True

    def test_key_rotation_config_custom_values(self):
        config = KeyRotationConfig(
            rotation_interval_days=90,
            grace_period_days=14,
            max_active_keys=3,
            auto_rotate=False,
        )
        assert config.rotation_interval_days == 90
        assert config.grace_period_days == 14
        assert config.max_active_keys == 3
        assert config.auto_rotate is False


# ── KeyVersion / KeyStatus ─────────────────────────────────────────────────


class TestKeyVersion:
    def test_key_version_creation(self):
        key = KeyVersion(
            key_id="k1",
            created_at=1.0,
            expires_at=None,
            status=KeyStatus.ACTIVE,
            key_data=b"data",
        )
        assert key.key_id == "k1"
        assert key.created_at == 1.0
        assert key.expires_at is None
        assert key.status == KeyStatus.ACTIVE
        assert key.key_data == b"data"

    def test_key_status_enum_values(self):
        assert KeyStatus.ACTIVE.value == "active"
        assert KeyStatus.RETIRED.value == "retired"
        assert KeyStatus.EXPIRED.value == "expired"


# ── Secret store CRUD ──────────────────────────────────────────────────────


class TestSecretStore:
    def test_store_and_get(self):
        store = InMemorySecretStore()
        store.store("k1", b"secret")
        assert store.get("k1") == b"secret"

    def test_get_missing_returns_none(self):
        store = InMemorySecretStore()
        assert store.get("missing") is None

    def test_delete_removes_secret(self):
        store = InMemorySecretStore()
        store.store("k1", b"secret")
        store.delete("k1")
        assert store.get("k1") is None

    def test_list_secrets(self):
        store = InMemorySecretStore()
        store.store("k1", b"a")
        store.store("k2", b"b")
        assert sorted(store.list_secrets()) == ["k1", "k2"]

    def test_store_overwrite(self):
        store = InMemorySecretStore()
        store.store("k1", b"old")
        store.store("k1", b"new")
        assert store.get("k1") == b"new"

    def test_secret_store_is_abstract(self):
        with pytest.raises(TypeError):
            SecretStore()  # type: ignore[abstract]


# ── Rotation policy ─────────────────────────────────────────────────────────


class TestRotationPolicy:
    def test_policy_creation(self):
        policy = SecretRotationPolicy(
            name="monthly",
            interval_days=30,
            auto_rotate=True,
            notification_channels=["email", "slack"],
        )
        assert policy.name == "monthly"
        assert policy.interval_days == 30
        assert policy.auto_rotate is True
        assert policy.notification_channels == ["email", "slack"]

    def test_should_rotate_no_last_rotation(self):
        policy = SecretRotationPolicy("p", 30, True)
        assert should_rotate(None, policy) is True

    def test_should_rotate_within_interval(self):
        policy = SecretRotationPolicy("p", 30, True)
        now = time.time()
        assert should_rotate(now - 10 * DAY, policy, now=now) is False

    def test_should_rotate_past_interval(self):
        policy = SecretRotationPolicy("p", 30, True)
        now = time.time()
        assert should_rotate(now - 31 * DAY, policy, now=now) is True

    def test_get_next_rotation_date(self):
        policy = SecretRotationPolicy("p", 30, True)
        assert get_next_rotation_date(1000.0, policy) == 1000.0 + 30 * DAY

    def test_get_next_rotation_date_no_last_rotation(self):
        policy = SecretRotationPolicy("p", 30, True)
        assert get_next_rotation_date(None, policy) is None
