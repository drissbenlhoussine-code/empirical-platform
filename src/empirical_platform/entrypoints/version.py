"""Version placeholder entrypoint."""

from __future__ import annotations

import json

from empirical_platform import __version__


def version_payload() -> dict[str, str]:
    """Return package version metadata."""
    return {"version": __version__}


def main() -> None:
    """Print version JSON."""
    print(json.dumps(version_payload(), sort_keys=True))


if __name__ == "__main__":
    main()
