#!/usr/bin/env python3
"""Build a deterministic source ZIP from the staged/tracked review files."""
from pathlib import Path
import hashlib
import subprocess
import zipfile


def main():
    root = Path(__file__).resolve().parents[1]
    files = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    output = root / "site/assets/voxroom-review-source.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(filter(None, files)):
            if name in {"site/assets/voxroom-review-source.zip", "site/assets/voxroom-review-source.zip.sha256"}:
                continue
            # Image sheets are generated from the original videos included below.
            if name.startswith("site/assets/playback/"):
                continue
            path = root / name
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"source archive requires regular files: {name}")
            info = zipfile.ZipInfo("voxroom/" + name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(f"{digest}  {output.name}\n")
    print(f"Built {output.name}: {output.stat().st_size} bytes; SHA-256 {digest}")


if __name__ == "__main__":
    main()
