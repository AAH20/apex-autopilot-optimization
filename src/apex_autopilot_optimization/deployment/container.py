"""Container configuration and Dockerfile/docker-compose generation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ContainerConfig:
    """Container image and runtime configuration."""

    image: str
    tag: str
    registry: str
    ports: list[int] = field(default_factory=list)
    env_vars: dict[str, str] = field(default_factory=dict)
    resources: dict[str, str] = field(default_factory=dict)
    health_check: str = "/healthz"

    @property
    def full_image(self) -> str:
        """Return the fully-qualified image reference."""
        return f"{self.registry}/{self.image}:{self.tag}"


def generate_dockerfile(config: ContainerConfig) -> str:
    """Generate a Dockerfile from a ContainerConfig."""
    lines = [
        "FROM python:3.11-slim",
        "",
        "WORKDIR /app",
        "",
        "COPY pyproject.toml .",
        "COPY src/ src/",
        "",
        "RUN pip install --no-cache-dir .",
        "",
    ]

    for key, value in config.env_vars.items():
        lines.append(f'ENV {key}="{value}"')

    if config.env_vars:
        lines.append("")

    for port in config.ports:
        lines.append(f"EXPOSE {port}")

    lines.append("")

    if config.health_check:
        lines.append(
            f'HEALTHCHECK --interval=30s --timeout=5s --start-period=10s '
            f'CMD curl -f http://localhost:{config.ports[0] if config.ports else 8080}{config.health_check} || exit 1'
        )
        lines.append("")

    lines.append('CMD ["apex-autopilot", "serve"]')

    return "\n".join(lines) + "\n"


def generate_docker_compose(config: ContainerConfig) -> str:
    """Generate a docker-compose service definition from a ContainerConfig."""
    lines = [
        "services:",
        f"  {config.image}:",
        f"    image: {config.full_image}",
        "    restart: unless-stopped",
    ]

    if config.ports:
        lines.append("    ports:")
        for port in config.ports:
            lines.append(f'      - "{port}:{port}"')

    if config.env_vars:
        lines.append("    environment:")
        for key, value in config.env_vars.items():
            lines.append(f"      {key}: {value}")

    if config.health_check:
        lines.append("    healthcheck:")
        lines.append(f'      test: ["CMD", "curl", "-f", "http://localhost:{config.ports[0] if config.ports else 8080}{config.health_check}"]')
        lines.append("      interval: 30s")
        lines.append("      timeout: 5s")
        lines.append("      retries: 3")

    return "\n".join(lines) + "\n"
