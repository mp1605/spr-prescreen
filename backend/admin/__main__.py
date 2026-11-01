"""Local terminal credential setup only. Passwords never enter command arguments or logs."""

import argparse
import getpass
from pathlib import Path

from backend.security.auth import AuthFailure, initialize_admin


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Initialize or explicitly reset the local SPR admin."
    )
    parser.add_argument("operation", choices=("init", "reset"))
    args = parser.parse_args()
    try:
        password = getpass.getpass("New admin password (12–1024 characters): ")
        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            raise AuthFailure("Passwords do not match.")
        initialize_admin(
            Path(__file__).resolve().parents[2], password, reset=args.operation == "reset"
        )
    except (AuthFailure, OSError, EOFError, KeyboardInterrupt) as exc:
        print(str(exc) or "Admin setup cancelled.")
        return 2
    print("Local admin configured. Existing sessions are invalidated. Sign in on the Rules page.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
