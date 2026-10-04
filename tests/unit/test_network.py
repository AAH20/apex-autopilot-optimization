"""Tests for network security module."""
from __future__ import annotations

import pytest

from apex_autopilot_optimization.network import (
    TLSConfig,
    TLSSocket,
    CertificateManager,
    NetworkPolicy,
    FirewallRule,
    check_allowed,
)


class TestTLSConfig:
    """Tests for TLSConfig dataclass."""

    def test_creation_with_all_fields(self) -> None:
        config = TLSConfig(
            cert_path="/tmp/cert.pem",
            key_path="/tmp/key.pem",
            ca_path="/tmp/ca.pem",
            verify_mode="CERT_REQUIRED",
            min_version="TLSv1_2",
        )
        assert config.cert_path == "/tmp/cert.pem"
        assert config.key_path == "/tmp/key.pem"
        assert config.ca_path == "/tmp/ca.pem"
        assert config.verify_mode == "CERT_REQUIRED"
        assert config.min_version == "TLSv1_2"

    def test_creation_with_defaults(self) -> None:
        config = TLSConfig()
        assert config.cert_path == ""
        assert config.key_path == ""
        assert config.ca_path == ""
        assert config.verify_mode == "CERT_REQUIRED"
        assert config.min_version == "TLSv1_2"


class TestTLSSocket:
    """Tests for TLSSocket class."""

    def test_creation(self) -> None:
        config = TLSConfig()
        sock = TLSSocket(config)
        assert sock is not None
        assert sock.config is config

    def test_has_required_methods(self) -> None:
        config = TLSConfig()
        sock = TLSSocket(config)
        assert hasattr(sock, "connect")
        assert hasattr(sock, "handshake")
        assert hasattr(sock, "send")
        assert hasattr(sock, "recv")
        assert hasattr(sock, "close")

    def test_connect_refused(self) -> None:
        config = TLSConfig()
        sock = TLSSocket(config)
        with pytest.raises((ConnectionError, OSError)):
            sock.connect("127.0.0.1", 1)


class TestCertificateManager:
    """Tests for CertificateManager class."""

    def test_generate_self_signed(self, tmp_path) -> None:
        mgr = CertificateManager()
        cert_path = tmp_path / "cert.pem"
        key_path = tmp_path / "key.pem"
        mgr.generate_self_signed(str(cert_path), str(key_path), "localhost")
        assert cert_path.exists()
        assert key_path.exists()

    def test_load_identity(self, tmp_path) -> None:
        mgr = CertificateManager()
        cert_path = tmp_path / "cert.pem"
        key_path = tmp_path / "key.pem"
        mgr.generate_self_signed(str(cert_path), str(key_path), "localhost")
        identity = mgr.load_identity(str(cert_path), str(key_path))
        assert identity is not None

    def test_verify_peer(self, tmp_path) -> None:
        mgr = CertificateManager()
        cert_path = tmp_path / "cert.pem"
        key_path = tmp_path / "key.pem"
        mgr.generate_self_signed(str(cert_path), str(key_path), "localhost")
        result = mgr.verify_peer(str(cert_path))
        assert result is True

    def test_get_cert_info(self, tmp_path) -> None:
        mgr = CertificateManager()
        cert_path = tmp_path / "cert.pem"
        key_path = tmp_path / "key.pem"
        mgr.generate_self_signed(str(cert_path), str(key_path), "localhost")
        info = mgr.get_cert_info(str(cert_path))
        assert info is not None
        assert "subject" in info
        assert "issuer" in info

    def test_rotate_certificates(self, tmp_path) -> None:
        mgr = CertificateManager()
        cert_path = tmp_path / "cert.pem"
        key_path = tmp_path / "key.pem"
        mgr.generate_self_signed(str(cert_path), str(key_path), "localhost")
        old_info = mgr.get_cert_info(str(cert_path))
        mgr.rotate_certificates(str(cert_path), str(key_path), "localhost")
        new_info = mgr.get_cert_info(str(cert_path))
        assert new_info is not None
        assert new_info["serial_number"] != old_info["serial_number"]

    def test_load_nonexistent_identity(self, tmp_path) -> None:
        mgr = CertificateManager()
        with pytest.raises((FileNotFoundError, ValueError)):
            mgr.load_identity(
                str(tmp_path / "nonexistent.pem"),
                str(tmp_path / "nonexistent.key"),
            )


class TestNetworkPolicy:
    """Tests for NetworkPolicy and check_allowed."""

    def test_policy_creation(self) -> None:
        policy = NetworkPolicy(
            name="test-policy",
            allowed_hosts=["localhost", "127.0.0.1"],
            allowed_ports=[443, 8443],
            denied_hosts=["evil.com"],
            denied_ports=[22],
        )
        assert policy.name == "test-policy"
        assert "localhost" in policy.allowed_hosts
        assert 443 in policy.allowed_ports
        assert "evil.com" in policy.denied_hosts
        assert 22 in policy.denied_ports

    def test_check_allowed_permitted(self) -> None:
        policy = NetworkPolicy(
            name="test",
            allowed_hosts=["localhost"],
            allowed_ports=[443],
            denied_hosts=[],
            denied_ports=[],
        )
        assert check_allowed(policy, "localhost", 443) is True

    def test_check_allowed_denied_host(self) -> None:
        policy = NetworkPolicy(
            name="test",
            allowed_hosts=["localhost"],
            allowed_ports=[443],
            denied_hosts=["evil.com"],
            denied_ports=[],
        )
        assert check_allowed(policy, "evil.com", 443) is False

    def test_check_allowed_denied_port(self) -> None:
        policy = NetworkPolicy(
            name="test",
            allowed_hosts=["localhost"],
            allowed_ports=[443],
            denied_hosts=[],
            denied_ports=[22],
        )
        assert check_allowed(policy, "localhost", 22) is False

    def test_check_allowed_not_in_allowed_list(self) -> None:
        policy = NetworkPolicy(
            name="test",
            allowed_hosts=["localhost"],
            allowed_ports=[443],
            denied_hosts=[],
            denied_ports=[],
        )
        assert check_allowed(policy, "other.com", 443) is False


class TestFirewallRule:
    """Tests for FirewallRule."""

    def test_creation(self) -> None:
        rule = FirewallRule(
            action="ALLOW",
            protocol="tcp",
            source="192.168.1.0/24",
            destination="10.0.0.1",
            port=443,
        )
        assert rule.action == "ALLOW"
        assert rule.protocol == "tcp"
        assert rule.source == "192.168.1.0/24"
        assert rule.destination == "10.0.0.1"
        assert rule.port == 443

    def test_matches(self) -> None:
        rule = FirewallRule(
            action="ALLOW",
            protocol="tcp",
            source="192.168.1.0/24",
            destination="10.0.0.1",
            port=443,
        )
        assert rule.matches("192.168.1.0/24", "10.0.0.1", 443, "tcp") is True
        assert rule.matches("10.0.0.0/8", "10.0.0.1", 443, "tcp") is False
        assert rule.matches("192.168.1.0/24", "10.0.0.1", 80, "tcp") is False
        assert rule.matches("192.168.1.0/24", "10.0.0.1", 443, "udp") is False
