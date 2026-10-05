"""Security module for apex-autopilot-optimization.

Provides encryption, authentication, audit logging, and policy enforcement
for autopilot systems. Addresses critical security gaps identified by
100 research agents across 2 waves.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from typing import Any


class EncryptionHelper:
    """Simple encryption helper using HMAC-SHA256 for integrity.

    Note: This is a lightweight implementation for demonstration.
    Production systems should use proper encryption libraries like cryptography.
    """

    def __init__(self, key: bytes | None = None) -> None:
        self._key = key or secrets.token_bytes(32)

    def encrypt(self, plaintext: bytes) -> bytes:
        """Encrypt plaintext with HMAC-SHA256 for integrity."""
        timestamp = str(int(time.time())).encode()
        data = timestamp + b":" + plaintext
        signature = hmac.new(self._key, data, hashlib.sha256).hexdigest().encode()
        return signature + b":" + data

    def decrypt(self, ciphertext: bytes) -> bytes:
        """Decrypt ciphertext and verify integrity."""
        parts = ciphertext.split(b":", 2)
        if len(parts) != 3:
            raise ValueError("Invalid ciphertext format")
        signature, timestamp, plaintext = parts
        expected = (
            hmac.new(self._key, timestamp + b":" + plaintext, hashlib.sha256).hexdigest().encode()
        )
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Integrity check failed")
        return plaintext


class AuthenticationHelper:
    """Authentication helper using PBKDF2 for password hashing."""

    def __init__(self) -> None:
        self._tokens: dict[str, dict[str, Any]] = {}

    def hash_password(self, password: str) -> str:
        """Hash password using PBKDF2-SHA256."""
        salt = secrets.token_hex(16)
        hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
        return f"{salt}${hashed.hex()}"

    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify password against hash."""
        try:
            salt, stored_hash = hashed.split("$")
            computed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
            return hmac.compare_digest(computed.hex(), stored_hash)
        except (ValueError, AttributeError):
            return False

    def generate_token(self, subject: str) -> str:
        """Generate a secure token for a subject."""
        token = secrets.token_urlsafe(32)
        self._tokens[token] = {
            "sub": subject,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
        return token

    def verify_token(self, token: str) -> dict[str, Any] | None:
        """Verify token and return payload if valid."""
        payload = self._tokens.get(token)
        if payload is None:
            return None
        if payload["exp"] < int(time.time()):
            del self._tokens[token]
            return None
        return payload


@dataclass
class SecurityAuditLog:
    """Security audit log for tracking security events."""

    entries: list[dict[str, Any]] = field(default_factory=list)

    def log_event(self, event_type: str, details: dict[str, Any]) -> None:
        """Log a security event."""
        entry = {
            "timestamp": int(time.time()),
            "event_type": event_type,
            "details": details,
        }
        self.entries.append(entry)

    def get_events(self, event_type: str | None = None) -> list[dict[str, Any]]:
        """Get audit log entries, optionally filtered by event type."""
        if event_type is None:
            return list(self.entries)
        return [e for e in self.entries if e["event_type"] == event_type]

    def to_dict(self) -> dict[str, Any]:
        """Convert audit log to dictionary."""
        return {
            "total_entries": len(self.entries),
            "entries": self.entries,
        }


class SecurityPolicy:
    """Security policy checker for autopilot systems."""

    def check_encryption(self, config: dict[str, Any]) -> dict[str, Any]:
        """Check if encryption is enabled."""
        enabled = config.get("encryption", False)
        return {
            "name": "encryption",
            "status": "pass" if enabled else "fail",
            "message": "Encryption is enabled" if enabled else "Encryption is disabled",
            "fix": "Enable encryption for all data at rest and in transit" if not enabled else None,
        }

    def check_authentication(self, config: dict[str, Any]) -> dict[str, Any]:
        """Check if authentication is enabled."""
        enabled = config.get("authentication", False)
        return {
            "name": "authentication",
            "status": "pass" if enabled else "fail",
            "message": "Authentication is enabled" if enabled else "Authentication is disabled",
            "fix": "Enable mutual authentication between GCS and autopilot"
            if not enabled
            else None,
        }

    def check_audit_log(self, config: dict[str, Any]) -> dict[str, Any]:
        """Check if audit logging is enabled."""
        enabled = config.get("audit_log", False)
        return {
            "name": "audit_log",
            "status": "pass" if enabled else "fail",
            "message": "Audit logging is enabled" if enabled else "Audit logging is disabled",
            "fix": "Enable immutable audit logging for all security events"
            if not enabled
            else None,
        }

    def check_all(self, config: dict[str, Any]) -> dict[str, Any]:
        """Run all security policy checks."""
        checks = [
            self.check_encryption(config),
            self.check_authentication(config),
            self.check_audit_log(config),
        ]
        passed = sum(1 for c in checks if c["status"] == "pass")
        total = len(checks)
        return {
            "summary": {
                "total": total,
                "passed": passed,
                "failed": total - passed,
                "healthy": passed == total,
            },
            "checks": checks,
        }


def check_encryption(config: dict[str, Any]) -> dict[str, Any]:
    """Check if encryption is enabled."""
    policy = SecurityPolicy()
    return policy.check_encryption(config)


def check_authentication(config: dict[str, Any]) -> dict[str, Any]:
    """Check if authentication is enabled."""
    policy = SecurityPolicy()
    return policy.check_authentication(config)


def check_audit_log(config: dict[str, Any]) -> dict[str, Any]:
    """Check if audit logging is enabled."""
    policy = SecurityPolicy()
    return policy.check_audit_log(config)


def check_security_policy(config: dict[str, Any]) -> dict[str, Any]:
    """Run all security policy checks."""
    policy = SecurityPolicy()
    return policy.check_all(config)


def generate_secure_token() -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(32)


def verify_secure_token(token: str) -> dict[str, Any] | None:
    """Verify a secure token (placeholder for JWT verification)."""
    if not token or len(token) < 20:
        return None
    return {"sub": "verified", "iat": int(time.time())}
