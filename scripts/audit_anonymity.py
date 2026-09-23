#!/usr/bin/env python3
"""Inspect tracked review files; private identity terms are supplied externally."""
from __future__ import annotations

import argparse
import io
from pathlib import Path
import re
import subprocess
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terms-file", type=Path, help="Private UTF-8 file, one identifying term per line; keep outside this repository")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    terms = [] if args.terms_file is None else [v.strip().casefold() for v in args.terms_file.read_text().splitlines() if v.strip()]
    paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    findings = []
    patterns = [
        ("absolute home path", re.compile(r"/(?:home|Users)/[A-Za-z0-9_.-]+/")),
        ("private IPv4 address", re.compile(r"\b(?:192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+)\b")),
        ("private key", re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----")),
    ]

    def inspect(name, data, nested=False):
        text = data.decode("utf-8", errors="ignore")
        folded = (name + "\n" + text).casefold()
        if any(term in folded for term in terms):
            findings.append((name, "private identity term"))
        for reason, pattern in patterns:
            if pattern.search(text):
                findings.append((name, reason))
        if name.endswith(".zip") and not nested:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for member in archive.infolist():
                    inspect(name + "::" + member.filename, archive.read(member), True)

    count = 0
    for name in filter(None, paths):
        path = root / name
        if path.is_symlink():
            findings.append((name, "symbolic link"))
        elif path.is_file():
            inspect(name, path.read_bytes())
            count += 1
    history = subprocess.run(["git", "log", "--all", "--format=%an <%ae>|%cn <%ce>"], cwd=root, capture_output=True, text=True)
    if history.returncode == 0:
        for value in history.stdout.splitlines():
            if value != "Anonymous Authors <anonymous@example.invalid>|Anonymous Authors <anonymous@example.invalid>":
                findings.append(("git history", "nonanonymous author or committer"))
    for name, reason in findings:
        print(f"FAIL {name}: {reason}")
    print(f"Scanned {count} tracked files and nested source archive; {len(findings)} findings.")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
