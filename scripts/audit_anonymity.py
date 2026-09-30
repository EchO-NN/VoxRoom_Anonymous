#!/usr/bin/env python3
"""Check review files for identifying text, local paths, and embedded archives."""
from __future__ import annotations

import argparse
import base64
import io
from pathlib import Path
import re
import subprocess
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terms-file", type=Path, help="Private UTF-8 file, one identifying term per line; keep outside this repository")
    parser.add_argument("--check-history", action="store_true", help="Also check Git author and committer identities")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    terms = [] if args.terms_file is None else [v.strip().casefold() for v in args.terms_file.read_text().splitlines() if v.strip()]
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, text=True)
    if tracked.returncode == 0:
        paths = list(filter(None, tracked.stdout.split("\0")))
    else:
        excluded = {".git", ".venv", "__pycache__", ".pytest_cache", "outputs", "build", "dist"}
        paths = [str(path.relative_to(root)) for path in root.rglob("*")
                 if path.is_file() and not excluded.intersection(path.relative_to(root).parts)
                 and not path.name.endswith((".pyc", ".pyo"))]
    findings = []
    patterns = [
        ("absolute home path", re.compile(r"/(?:home|Users)/[A-Za-z0-9_.-]+/")),
        ("private IPv4 address", re.compile(r"\b(?:192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+)\b")),
        ("private key", re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----")),
    ]

    def inspect(name, data, nested=False):
        if name.endswith(".zip") and not nested:
            # Inspect the extracted content and metadata. Compressed bytes can
            # accidentally spell short identity terms when decoded as text.
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                inspect(name, archive.comment, True)
                for member in archive.infolist():
                    member_name = name + "::" + member.filename
                    inspect(member_name, archive.read(member), True)
                    if member.comment or member.extra:
                        inspect(member_name + "::metadata", member.comment + member.extra, True)
            return
        text = data.decode("utf-8", errors="ignore")
        if name.lower().endswith((".svg", ".css")):
            def inspect_embedded(match):
                # Encoded resource bytes can coincidentally spell identity terms;
                # inspect the decoded payload and retain its MIME type instead.
                inspect(name + "::embedded-resource", base64.b64decode(match[2]), True)
                return "data:" + match[1] + ";base64,[inspected]"
            text = re.sub(r"data:([^;,\s]+);base64,([A-Za-z0-9+/=\s]+)", inspect_embedded, text)
        folded = (name + "\n" + text).casefold()
        if any(term in folded for term in terms):
            findings.append((name, "private identity term"))
        for reason, pattern in patterns:
            if pattern.search(text):
                findings.append((name, reason))

    count = 0
    for name in filter(None, paths):
        path = root / name
        if path.is_symlink():
            findings.append((name, "symbolic link"))
        elif path.is_file():
            inspect(name, path.read_bytes())
            count += 1
    if args.check_history:
        history = subprocess.run(["git", "log", "--all", "--format=%an <%ae>|%cn <%ce>"], cwd=root, capture_output=True, text=True)
        if history.returncode != 0:
            findings.append(("git history", "no Git history available"))
        else:
            for value in history.stdout.splitlines():
                if value != "Anonymous Authors <anonymous@example.invalid>|Anonymous Authors <anonymous@example.invalid>":
                    findings.append(("git history", "nonanonymous author or committer"))
    for name, reason in findings:
        print(f"FAIL {name}: {reason}")
    print(f"Scanned {count} files and embedded archives; {len(findings)} findings.")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
