"""Static health placeholder entrypoint."""

from __future__ import annotations

import json

from empirical_platform.shared.config.settings import load_settings
from empirical_platform.shared.logging.configure import configure_logging


def health_payload() -> dict[str, str]:
    """Return a static foundation health payload."""
    settings = load_settings()
    configure_logging(settings.logging)
    return {"status": "ok", "environment": settings.app.environment}


def main() -> None:
    """Print static health JSON."""
    print(json.dumps(health_payload(), sort_keys=True))


if __name__ == "__main__":
    main()
