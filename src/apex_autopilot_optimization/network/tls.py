"""TLS configuration and socket wrapper for secure communications."""
from __future__ import annotations

import socket
import ssl
from dataclasses import dataclass


@dataclass
class TLSConfig:
    """Configuration for TLS-secured connections."""

    cert_path: str = ""
    key_path: str = ""
    ca_path: str = ""
    verify_mode: str = "CERT_REQUIRED"
    min_version: str = "TLSv1_2"


class TLSSocket:
    """TLS-wrapped socket for encrypted network communication."""

    def __init__(self, config: TLSConfig) -> None:
        self.config = config
        self._sock: ssl.SSLSocket | None = None
        self._raw_sock: socket.socket | None = None

    def _create_ssl_context(self) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        verify_modes = {
            "CERT_NONE": ssl.CERT_NONE,
            "CERT_OPTIONAL": ssl.CERT_OPTIONAL,
            "CERT_REQUIRED": ssl.CERT_REQUIRED,
        }
        context.verify_mode = verify_modes.get(self.config.verify_mode, ssl.CERT_REQUIRED)
        min_versions = {
            "TLSv1": ssl.TLSVersion.TLSv1,
            "TLSv1_1": ssl.TLSVersion.TLSv1_1,
            "TLSv1_2": ssl.TLSVersion.TLSv1_2,
            "TLSv1_3": ssl.TLSVersion.TLSv1_3,
        }
        if self.config.min_version in min_versions:
            context.minimum_version = min_versions[self.config.min_version]
        if self.config.cert_path and self.config.key_path:
            context.load_cert_chain(self.config.cert_path, self.config.key_path)
        if self.config.ca_path:
            context.load_verify_locations(self.config.ca_path)
        return context

    def connect(self, host: str, port: int) -> None:
        """Establish a TCP connection and wrap it with TLS."""
        raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw.connect((host, port))
        context = self._create_ssl_context()
        self._sock = context.wrap_socket(raw, server_hostname=host)
        self._raw_sock = raw

    def handshake(self) -> None:
        """Perform (or redo) the TLS handshake."""
        if self._sock is None:
            raise ConnectionError("Socket is not connected")
        self._sock.do_handshake()

    def send(self, data: bytes) -> int:
        """Send data over the TLS connection."""
        if self._sock is None:
            raise ConnectionError("Socket is not connected")
        return self._sock.send(data)

    def recv(self, bufsize: int) -> bytes:
        """Receive data from the TLS connection."""
        if self._sock is None:
            raise ConnectionError("Socket is not connected")
        return self._sock.recv(bufsize)

    def close(self) -> None:
        """Close the TLS connection."""
        if self._sock is not None:
            self._sock.close()
            self._sock = None
        if self._raw_sock is not None:
            self._raw_sock.close()
            self._raw_sock = None
