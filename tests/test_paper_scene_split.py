import copy
import csv
import json

import pytest

from voxroom_online.isaac_runtime.door_seed_learning.scene_split import (
    PAPER_SPLIT_COUNTS, build_paper_scene_split, validate_paper_scene_split,
)
from voxroom_online.isaac_runtime.scripts.create_door_seed_scene_split import main as split_main
from voxroom_online.isaac_runtime.scripts.build_door_seed_dataset import _load_splits, main as dataset_main


def manifest_rows():
    return [
        {"scene_id": f"{dataset}_{split}_{i:03d}", "dataset": dataset, "split": split}
        for dataset, counts in PAPER_SPLIT_COUNTS.items()
        for split, count in counts.items() for i in range(count)
    ]


def test_explicit_scene_manifest_round_trips_into_dataset_builder(tmp_path):
    rows = manifest_rows()
    manifest = tmp_path / 'scenes.csv'
    with manifest.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['scene_id', 'dataset', 'split'])
        writer.writeheader()
        writer.writerows(reversed(rows))
    target = tmp_path / 'split.json'
    assert split_main(['--manifest', str(manifest), '--out', str(target)]) == 0
    loaded = _load_splits(str(target))
    assert loaded == {r['scene_id']: r['split'] for r in rows}
    payload = json.loads(target.read_text())
    assert payload['counts_by_dataset'] == PAPER_SPLIT_COUNTS
    assert payload['counts']['train'] == 16
    assert payload['counts']['val'] == 4
    assert payload['counts']['test'] == 74
    assert len((tmp_path / 'train.txt').read_text().splitlines()) == 16
    assert 'seed' not in payload and 'dataset_root' not in payload


def test_total_counts_do_not_hide_wrong_dataset_ratios():
    rows = manifest_rows()
    train_ia = next(r for r in rows if r['dataset'] == 'interioragent' and r['split'] == 'train')
    test_gr = next(r for r in rows if r['dataset'] == 'grscene' and r['split'] == 'test')
    train_ia['split'], test_gr['split'] = test_gr['split'], train_ia['split']
    with pytest.raises(ValueError, match='paper scene counts'):
        build_paper_scene_split(rows)


def test_manifest_rejects_overlapping_or_duplicate_physical_scene_ids():
    rows = manifest_rows()
    rows.append({**rows[0], 'split': 'test'})
    with pytest.raises(ValueError, match='duplicate scene_id'):
        build_paper_scene_split(rows)
    rows[-1] = dict(rows[0])
    with pytest.raises(ValueError, match='duplicate scene_id'):
        build_paper_scene_split(rows)


def test_split_json_rejects_overlap_and_duplicate_list_entries():
    original = build_paper_scene_split(manifest_rows())
    overlap = copy.deepcopy(original)
    overlap['test'][0] = overlap['train'][0]
    with pytest.raises(ValueError, match='overlap'):
        validate_paper_scene_split(overlap)
    duplicate = copy.deepcopy(original)
    duplicate['train'].append(duplicate['train'][0])
    with pytest.raises(ValueError, match='duplicate scene IDs'):
        validate_paper_scene_split(duplicate)


def test_dataset_creation_requires_explicit_split_file():
    with pytest.raises(SystemExit) as error:
        dataset_main(['--collection-root', 'unused', '--out-dir', 'unused'])
    assert error.value.code == 2
