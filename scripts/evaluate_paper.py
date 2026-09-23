#!/usr/bin/env python3
"""Score room label maps and aggregate snapshots with the manuscript protocol.

The only runtime dependencies are NumPy and SciPy. Input scores are fractions,
and output summary scores are percentages. No simulator or model is imported.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import statistics

import numpy as np
from scipy.optimize import linear_sum_assignment

STAGES = ("20", "40", "60", "70", "80", "90", "final")
METRICS = ("precision", "recall", "f1", "room_miou")
IDENTIFIERS = ("method", "dataset", "scene_id", "trajectory_id", "stage")
PAPER_STAGE_COUNTS = dict(zip(STAGES, (370, 370, 370, 370, 370, 348, 370)))


def _labels(value, name):
    arr = np.asarray(value)
    if arr.ndim != 2 or arr.dtype.kind not in "iu" or np.any(arr < 0):
        raise ValueError(f"{name} must be a two-dimensional nonnegative integer label map")
    return arr


def score_snapshot(gt_labels, pred_labels, sfm_free):
    """Eqs. (9)-(10), restricted to currently observed structural-free cells.

    Label zero means unassigned. All cells in the shared evaluation domain must
    have a positive final ground-truth room ID. Disconnected pieces retain their
    room ID. No area threshold is applied because none is specified in the paper.
    """
    gt = _labels(gt_labels, "gt_labels")
    pred = _labels(pred_labels, "pred_labels")
    domain = np.asarray(sfm_free)
    if gt.shape != pred.shape or gt.shape != domain.shape:
        raise ValueError("gt_labels, pred_labels, and sfm_free must have equal shapes")
    if not np.isin(domain, (0, 1)).all():
        raise ValueError("sfm_free must contain only boolean or binary values")
    domain = domain.astype(bool)
    if not domain.any():
        raise ValueError("an empty observed domain is not an evaluation snapshot")
    if np.any(domain & (gt == 0)):
        raise ValueError("every observed structural-free cell requires a ground-truth room ID")
    g = gt[domain]
    p = pred[domain]
    _, gi, ga = np.unique(g, return_inverse=True, return_counts=True)
    pl, pi, pa = np.unique(p, return_inverse=True, return_counts=True)
    intersections = np.bincount(
        gi * len(pl) + pi, minlength=len(ga) * len(pl)
    ).reshape(len(ga), len(pl)).astype(np.float64)
    positive = pl > 0
    intersections = intersections[:, positive]
    pa = pa[positive]
    if len(pa):
        precision = float(np.mean(intersections.max(axis=0) / pa))
        recall = float(np.mean(intersections.max(axis=1) / ga))
        union = ga[:, None] + pa[None, :] - intersections
        iou = intersections / union
        row, col = linear_sum_assignment(-iou)
        room_miou = float(iou[row, col].sum() / len(ga))
    else:
        precision = recall = room_miou = 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return dict(precision=precision, recall=recall, f1=f1, room_miou=room_miou,
                n_gt=len(ga), n_pred=len(pa), domain_cells=int(domain.sum()))


def normalize_rows(rows):
    normalized, seen = [], set()
    for index, original in enumerate(rows, 1):
        row = dict(original)
        for field in IDENTIFIERS:
            if not str(row.get(field, "")).strip():
                raise ValueError(f"row {index}: missing {field}")
            row[field] = str(row[field]).strip()
        row["stage"] = row["stage"].lower().removesuffix("%")
        if row["stage"] not in STAGES:
            raise ValueError(f"row {index}: stage must be one of {STAGES}; Final does not mean 100% coverage")
        identity = tuple(row[field] for field in IDENTIFIERS)
        if identity in seen:
            raise ValueError(f"duplicate method/scene/trajectory/stage: {identity}")
        seen.add(identity)
        for field in METRICS:
            try:
                value = float(row[field])
            except (KeyError, ValueError, TypeError) as error:
                raise ValueError(f"row {index}: invalid {field}") from error
            if not np.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"row {index}: {field} must be a finite fraction in [0, 1]")
            row[field] = value
        p, r = row["precision"], row["recall"]
        expected_f1 = 2 * p * r / (p + r) if p + r else 0.0
        if abs(row["f1"] - expected_f1) > 1e-8:
            raise ValueError(f"row {index}: F1 must be computed from P/R at this snapshot")
        normalized.append(row)
    if not normalized:
        raise ValueError("at least one snapshot is required")
    return normalized


def protocol_audit(rows):
    """Check the reported paper counts and a shared set of method snapshots.

    This checks manifest structure, not authenticity of observations, successful
    training, policy choice, ground truth, or independence of train/test scenes.
    """
    by_method = defaultdict(list)
    for row in rows:
        by_method[row["method"]].append(row)
    universe = {(r["dataset"], r["scene_id"], r["trajectory_id"], r["stage"]) for r in rows}
    reports = {}
    for method, samples in sorted(by_method.items()):
        trajectories = defaultdict(set)
        stages = Counter(r["stage"] for r in samples)
        scenes = defaultdict(set)
        for row in samples:
            scene = (row["dataset"], row["scene_id"])
            scenes[scene].add(row["trajectory_id"])
            trajectories[(*scene, row["trajectory_id"])].add(row["stage"])
        datasets = Counter(dataset for dataset, _ in scenes)
        observed = {(r["dataset"], r["scene_id"], r["trajectory_id"], r["stage"]) for r in samples}
        issues = []
        if dict(datasets) != {"interioragent": 15, "grscene": 59}:
            issues.append("expected 15 InteriorAgent and 59 GRScene test scenes")
        if any(len(ids) != 5 for ids in scenes.values()):
            issues.append("expected five trajectories per scene")
        if dict(stages) != PAPER_STAGE_COUNTS:
            issues.append("stage counts differ from the paper (370,370,370,370,370,348,370)")
        required = set(STAGES) - {"90"}
        if any(not required.issubset(values) for values in trajectories.values()):
            issues.append("one or more trajectories lack a required stage (90% may be absent)")
        if observed != universe:
            issues.append("methods do not share an identical snapshot universe")
        reports[method] = dict(scene_count=len(scenes), trajectory_count=len(trajectories),
                               snapshot_count=len(samples), scenes_by_dataset=dict(datasets),
                               stage_counts={stage: stages[stage] for stage in STAGES},
                               missing_shared_snapshots=len(universe - observed), issues=issues)
    return dict(paper_manifest_complete=all(not r["issues"] for r in reports.values()),
                methods=reports)


def _scene_balanced(samples):
    trajectories = defaultdict(list)
    for row in samples:
        trajectories[(row["dataset"], row["scene_id"], row["trajectory_id"])].append(row)
    scenes = defaultdict(list)
    for (dataset, scene, _), rows in trajectories.items():
        scenes[(dataset, scene)].append({metric: statistics.fmean(r[metric] for r in rows)
                                         for metric in METRICS})
    scene_scores = [{metric: statistics.fmean(t[metric] for t in values) for metric in METRICS}
                    for values in scenes.values()]
    return dict(snapshot_count=len(samples), trajectory_count=len(trajectories), scene_count=len(scenes),
                **{metric + "_percent": 100 * statistics.fmean(s[metric] for s in scene_scores)
                   for metric in METRICS})


def aggregate(rows):
    """Return stage/overall metrics and within-trajectory population stability."""
    rows = normalize_rows(rows)
    output, stability = [], []
    by_method = defaultdict(list)
    for row in rows:
        by_method[row["method"]].append(row)
    for method, samples in sorted(by_method.items()):
        for stage in (*STAGES, "average"):
            selected = samples if stage == "average" else [r for r in samples if r["stage"] == stage]
            if selected:
                output.append(dict(method=method, stage=stage, **_scene_balanced(selected)))
        trajectories = defaultdict(list)
        for row in samples:
            trajectories[(row["dataset"], row["scene_id"], row["trajectory_id"])].append(row["room_miou"])
        scenes = defaultdict(list)
        for (dataset, scene, _), values in trajectories.items():
            scenes[(dataset, scene)].append((statistics.pstdev(values), min(values)))
        scene_stats = [(statistics.fmean(t[0] for t in values), statistics.fmean(t[1] for t in values))
                       for values in scenes.values()]
        stability.append(dict(method=method, scene_count=len(scenes), trajectory_count=len(trajectories),
                              single_snapshot_trajectories=sum(len(v) == 1 for v in trajectories.values()),
                              room_miou_population_sd_pp=100 * statistics.fmean(t[0] for t in scene_stats),
                              room_miou_worst_stage_percent=100 * statistics.fmean(t[1] for t in scene_stats)))
    return output, stability, protocol_audit(rows)


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def score_manifest(path):
    """Each manifest row points to an NPZ with gt_labels/pred_labels/sfm_free."""
    rows = []
    path = Path(path).resolve()
    for row in read_csv(path):
        if not row.get("snapshot"):
            raise ValueError("snapshot manifest requires a snapshot column")
        snapshot = Path(row["snapshot"])
        if not snapshot.is_absolute():
            snapshot = path.parent / snapshot
        with np.load(snapshot, allow_pickle=False) as data:
            scores = score_snapshot(data["gt_labels"], data["pred_labels"], data["sfm_free"])
        rows.append({**{key: row[key] for key in IDENTIFIERS}, **scores})
    return normalize_rows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--snapshots", type=Path, help="CSV manifest of NPZ snapshots to score")
    source.add_argument("--scores", type=Path, help="CSV of already computed per-snapshot fractional scores")
    parser.add_argument("--out", type=Path, required=True, help="new output directory")
    parser.add_argument("--allow-incomplete", action="store_true", help="export diagnostics even when the paper manifest is incomplete")
    args = parser.parse_args()
    rows = score_manifest(args.snapshots) if args.snapshots else normalize_rows(read_csv(args.scores))
    summary, stability, audit = aggregate(rows)
    if not audit["paper_manifest_complete"] and not args.allow_incomplete:
        parser.exit(2, json.dumps(audit, indent=2) + "\nIncomplete paper manifest; use --allow-incomplete only for diagnostic exports.\n")
    args.out.mkdir(parents=True, exist_ok=False)
    write_csv(args.out / "snapshot_metrics.csv", rows)
    write_csv(args.out / "scene_balanced_metrics.csv", summary)
    write_csv(args.out / "stability.csv", stability)
    (args.out / "protocol_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(output=str(args.out), paper_manifest_complete=audit["paper_manifest_complete"])))


if __name__ == "__main__":
    main()
