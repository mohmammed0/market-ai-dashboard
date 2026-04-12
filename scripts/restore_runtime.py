from __future__ import annotations

import argparse
import sys
import tarfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore a Market AI runtime backup archive.")
    parser.add_argument("archive", help="Path to the .tar.gz backup archive.")
    parser.add_argument("--target-root", default=".", help="Workspace root to restore into.")
    parser.add_argument("--force", action="store_true", help="Allow overwriting existing files.")
    args = parser.parse_args()

    archive_path = Path(args.archive).resolve()
    target_root = Path(args.target_root).resolve()
    if not archive_path.exists():
        raise SystemExit(f"Backup archive not found: {archive_path}")

    target_root.mkdir(parents=True, exist_ok=True)

    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        if not args.force:
            collisions = []
            for member in members:
                destination = target_root / member.name
                if destination.exists():
                    collisions.append(str(destination))
            if collisions:
                preview = "\n".join(collisions[:10])
                raise SystemExit(
                    "Restore would overwrite existing files. Re-run with --force if this is intentional.\n"
                    f"{preview}"
                )
        archive.extractall(path=target_root)

    print(f"Restored backup into {target_root}")
    print("Review secrets handling separately if data/.settings.key was not restored.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
