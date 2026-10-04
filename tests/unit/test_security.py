"""Tests for security module."""

from apex_autopilot_optimization.security import (
    EncryptionHelper,
    AuthenticationHelper,
    SecurityAuditLog,
    SecurityPolicy,
    check_encryption,
    check_authentication,
    check_audit_log,
    check_security_policy,
    generate_secure_token,
    verify_secure_token,
)


class TestEncryptionHelper:
    """Tests for EncryptionHelper class."""

    def test_helper_creation(self):
        helper = EncryptionHelper()
        assert helper is not None

    def test_encrypt_decrypt(self):
        helper = EncryptionHelper()
        plaintext = b"test data"
        ciphertext = helper.encrypt(plaintext)
        assert ciphertext != plaintext
        decrypted = helper.decrypt(ciphertext)
        assert decrypted == plaintext

    def test_encrypt_empty(self):
        helper = EncryptionHelper()
        plaintext = b""
        ciphertext = helper.encrypt(plaintext)
        decrypted = helper.decrypt(ciphertext)
        assert decrypted == plaintext

    def test_encrypt_large_data(self):
        helper = EncryptionHelper()
        plaintext = b"x" * 10000
        ciphertext = helper.encrypt(plaintext)
        decrypted = helper.decrypt(ciphertext)
        assert decrypted == plaintext


class TestAuthenticationHelper:
    """Tests for AuthenticationHelper class."""

    def test_helper_creation(self):
        helper = AuthenticationHelper()
        assert helper is not None

    def test_hash_verify(self):
        helper = AuthenticationHelper()
        password = "test_password"
        hashed = helper.hash_password(password)
        assert hashed != password
        assert helper.verify_password(password, hashed) is True

    def test_verify_wrong_password(self):
        helper = AuthenticationHelper()
        password = "test_password"
        wrong_password = "wrong_password"
        hashed = helper.hash_password(password)
        assert helper.verify_password(wrong_password, hashed) is False

    def test_generate_token(self):
        helper = AuthenticationHelper()
        token = helper.generate_token("user123")
        assert token is not None
        assert len(token) > 0

    def test_verify_token(self):
        helper = AuthenticationHelper()
        token = helper.generate_token("user123")
        payload = helper.verify_token(token)
        assert payload is not None
        assert payload["sub"] == "user123"


class TestSecurityAuditLog:
    """Tests for SecurityAuditLog class."""

    def test_log_creation(self):
        log = SecurityAuditLog()
        assert log is not None

    def test_log_event(self):
        log = SecurityAuditLog()
        log.log_event("test_event", {"user": "test", "action": "login"})
        assert len(log.entries) == 1

    def test_log_multiple_events(self):
        log = SecurityAuditLog()
        log.log_event("event1", {"user": "test1"})
        log.log_event("event2", {"user": "test2"})
        assert len(log.entries) == 2

    def test_get_events(self):
        log = SecurityAuditLog()
        log.log_event("test_event", {"user": "test"})
        events = log.get_events()
        assert len(events) == 1
        assert events[0]["event_type"] == "test_event"


class TestSecurityPolicy:
    """Tests for SecurityPolicy class."""

    def test_policy_creation(self):
        policy = SecurityPolicy()
        assert policy is not None

    def test_check_encryption_enabled(self):
        policy = SecurityPolicy()
        result = policy.check_encryption({"encryption": True})
        assert result["status"] == "pass"

    def test_check_encryption_disabled(self):
        policy = SecurityPolicy()
        result = policy.check_encryption({"encryption": False})
        assert result["status"] == "fail"

    def test_check_authentication_enabled(self):
        policy = SecurityPolicy()
        result = policy.check_authentication({"authentication": True})
        assert result["status"] == "pass"

    def test_check_audit_log_enabled(self):
        policy = SecurityPolicy()
        result = policy.check_audit_log({"audit_log": True})
        assert result["status"] == "pass"


class TestCheckEncryption:
    """Tests for check_encryption function."""

    def test_returns_dict(self):
        result = check_encryption({"encryption": True})
        assert isinstance(result, dict)

    def test_pass_status(self):
        result = check_encryption({"encryption": True})
        assert result["status"] == "pass"

    def test_fail_status(self):
        result = check_encryption({"encryption": False})
        assert result["status"] == "fail"


class TestCheckAuthentication:
    """Tests for check_authentication function."""

    def test_returns_dict(self):
        result = check_authentication({"authentication": True})
        assert isinstance(result, dict)

    def test_pass_status(self):
        result = check_authentication({"authentication": True})
        assert result["status"] == "pass"


class TestCheckAuditLog:
    """Tests for check_audit_log function."""

    def test_returns_dict(self):
        result = check_audit_log({"audit_log": True})
        assert isinstance(result, dict)

    def test_pass_status(self):
        result = check_audit_log({"audit_log": True})
        assert result["status"] == "pass"


class TestCheckSecurityPolicy:
    """Tests for check_security_policy function."""

    def test_returns_dict(self):
        result = check_security_policy({})
        assert isinstance(result, dict)

    def test_checks_all_policies(self):
        config = {
            "encryption": True,
            "authentication": True,
            "audit_log": True,
        }
        result = check_security_policy(config)
        assert "summary" in result
        assert "checks" in result
        assert result["summary"]["total"] == 3
        assert result["summary"]["passed"] == 3
        assert result["summary"]["healthy"] is True


class TestGenerateSecureToken:
    """Tests for generate_secure_token function."""

    def test_returns_string(self):
        token = generate_secure_token()
        assert isinstance(token, str)

    def test_token_length(self):
        token = generate_secure_token()
        assert len(token) > 20

    def test_unique_tokens(self):
        token1 = generate_secure_token()
        token2 = generate_secure_token()
        assert token1 != token2


class TestVerifySecureToken:
    """Tests for verify_secure_token function."""

    def test_verify_valid_token(self):
        token = generate_secure_token()
        result = verify_secure_token(token)
        assert result is not None

    def test_verify_invalid_token(self):
        result = verify_secure_token("invalid_token")
        assert result is None
