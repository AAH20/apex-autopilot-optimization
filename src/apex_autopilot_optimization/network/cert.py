"""Certificate management: generation, loading, verification, rotation."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


class CertificateManager:
    """Manages TLS certificates for the autopilot network stack."""

    def generate_self_signed(self, cert_path: str, key_path: str, hostname: str) -> None:
        """Generate a self-signed certificate and private key on disk."""
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COMMON_NAME, hostname),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Apex Autopilot"),
            ]
        )
        now = datetime.datetime.now(datetime.UTC)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=365))
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName(hostname)]),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )
        cert_file = Path(cert_path)
        cert_file.parent.mkdir(parents=True, exist_ok=True)
        cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_file = Path(key_path)
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_bytes(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    def load_identity(self, cert_path: str, key_path: str) -> dict[str, Any]:
        """Load a certificate/key pair and return identity information."""
        cert_data = Path(cert_path).read_bytes()
        key_data = Path(key_path).read_bytes()
        cert = x509.load_pem_x509_certificate(cert_data)
        return {
            "cert_path": cert_path,
            "key_path": key_path,
            "subject": cert.subject.rfc4514_string(),
            "issuer": cert.issuer.rfc4514_string(),
            "serial_number": str(cert.serial_number),
            "not_valid_before": cert.not_valid_before_utc.isoformat(),
            "not_valid_after": cert.not_valid_after_utc.isoformat(),
            "key_size": len(key_data),
        }

    def verify_peer(self, cert_path: str) -> bool:
        """Verify a peer certificate is well-formed and currently valid."""
        try:
            cert = x509.load_pem_x509_certificate(Path(cert_path).read_bytes())
        except (ValueError, OSError):
            return False
        now = datetime.datetime.now(datetime.UTC)
        return cert.not_valid_before_utc <= now <= cert.not_valid_after_utc

    def rotate_certificates(self, cert_path: str, key_path: str, hostname: str) -> None:
        """Rotate certificates by generating a fresh self-signed pair."""
        self.generate_self_signed(cert_path, key_path, hostname)

    def get_cert_info(self, cert_path: str) -> dict[str, Any]:
        """Return descriptive information about a certificate."""
        cert = x509.load_pem_x509_certificate(Path(cert_path).read_bytes())
        return {
            "subject": cert.subject.rfc4514_string(),
            "issuer": cert.issuer.rfc4514_string(),
            "serial_number": str(cert.serial_number),
            "not_valid_before": cert.not_valid_before_utc.isoformat(),
            "not_valid_after": cert.not_valid_after_utc.isoformat(),
            "version": cert.version.name,
        }
