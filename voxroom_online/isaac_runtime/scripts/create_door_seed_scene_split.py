from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from voxroom_online.isaac_runtime.door_seed_learning.scene_split import (
    read_paper_scene_manifest,
    write_scene_split,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the explicit paper scene manifest and export its split JSON.")
    parser.add_argument("--manifest", required=True, help="CSV with scene_id,dataset,split; assignments must be supplied explicitly.")
    parser.add_argument("--out", required=True)
    parser.add_argument("--list-dir", default=None)
    args = parser.parse_args(argv)
    payload = read_paper_scene_manifest(args.manifest)
    write_scene_split(args.out, payload)

    list_dir = Path(args.list_dir).expanduser() if args.list_dir else Path(args.out).expanduser().parent
    list_dir.mkdir(parents=True, exist_ok=True)
    roles = dict(payload["roles"])
    lists = {
        "development_collection": roles["development_collection"],
        "heldout_validation": roles["heldout_validation"],
        "train": payload["train"],
        "val": payload["val"],
        "test": payload["test"],
    }
    for name, values in lists.items():
        (list_dir / (name + ".txt")).write_text("\n".join(values) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "counts": payload["counts"], "counts_by_dataset": payload["counts_by_dataset"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
