"""Verify the pinned official SDK archive before CI extraction; never opens a socket."""

import hashlib
import sys
from pathlib import Path

_EXPECTED_SHA256 = "673129e5cba58c4d77bc40647265f84ea42f605eccf88fa4c1221d62d12454f3"


def verify(path: Path) -> None:
    if hashlib.sha256(path.read_bytes()).hexdigest() != _EXPECTED_SHA256:
        raise ValueError("official SDK archive differs from reviewed 10.50.2 bytes")


if __name__ == "__main__":
    verify(Path(sys.argv[1]))
    print("Reviewed SDK archive digest verified")
