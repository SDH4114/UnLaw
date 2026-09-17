from __future__ import annotations

from collections.abc import Sequence

from unlawful.desktop.launcher import launch


def main(argv: Sequence[str] | None = None) -> int:
    return launch("minecraft", argv)


if __name__ == "__main__":
    raise SystemExit(main())
