"""Numerical examples that distinguish the manuscript protocol from pooling."""
import importlib.util
from pathlib import Path
import unittest

import numpy as np

SPEC = importlib.util.spec_from_file_location(
    "evaluate_paper", Path(__file__).resolve().parents[1] / "scripts" / "evaluate_paper.py"
)
evaluation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluation)


def row(scene, trajectory, stage, value, precision=None, recall=None):
    p = value if precision is None else precision
    r = value if recall is None else recall
    return dict(method="VoxRoom", dataset="example", scene_id=scene, trajectory_id=trajectory,
                stage=stage, precision=p, recall=r, f1=2 * p * r / (p + r) if p + r else 0,
                room_miou=value)


class PaperEvaluationTests(unittest.TestCase):
    def test_merge_and_split_have_distinct_overlap_and_assignment_scores(self):
        gt = np.array([[1, 1, 2, 2]])
        merged = evaluation.score_snapshot(gt, np.ones_like(gt), np.ones_like(gt, bool))
        self.assertEqual(merged["precision"], .5)
        self.assertEqual(merged["recall"], 1)
        self.assertAlmostEqual(merged["f1"], 2 / 3)
        self.assertEqual(merged["room_miou"], .25)
        split = evaluation.score_snapshot(np.ones_like(gt), gt, np.ones_like(gt, bool))
        self.assertEqual(split["precision"], 1)
        self.assertEqual(split["recall"], .5)
        self.assertEqual(split["room_miou"], .5)

    def test_domain_clipping_preserves_disconnected_gt_room_identity(self):
        gt = np.array([[9, 9, 9, 9, 9], [9, 9, 9, 9, 9]])
        mask = np.array([[1, 1, 0, 1, 1], [1, 1, 0, 1, 1]], bool)
        pred = np.array([[21, 21, 77, 22, 22], [21, 21, 77, 22, 22]])
        scores = evaluation.score_snapshot(gt, pred, mask)
        self.assertEqual(scores["n_gt"], 1)
        self.assertEqual(scores["n_pred"], 2)
        self.assertEqual(scores["room_miou"], .5)

    def test_unassigned_prediction_counts_as_missing_overlap(self):
        gt = np.ones((2, 2), int)
        scores = evaluation.score_snapshot(gt, np.zeros_like(gt), np.ones_like(gt, bool))
        self.assertEqual(scores["recall"], 0)
        self.assertEqual(scores["room_miou"], 0)

    def test_ground_truth_holes_cannot_silently_reduce_the_domain(self):
        with self.assertRaisesRegex(ValueError, "ground-truth"):
            evaluation.score_snapshot(np.array([[1, 0]]), np.array([[1, 1]]), np.array([[1, 1]]))

    def test_stage_then_trajectory_then_scene_weighting(self):
        rows = [row("a", "a1", "20", 0), row("a", "a1", "final", 1),
                row("a", "a2", "final", 1), row("b", "b1", "final", 0)]
        summaries, stability, audit = evaluation.aggregate(rows)
        overall = next(r for r in summaries if r["stage"] == "average")
        final = next(r for r in summaries if r["stage"] == "final")
        # Scene A: mean(mean(0,1), 1) = .75; scene B: 0; equal scene mean: .375.
        self.assertEqual(overall["room_miou_percent"], 37.5)
        self.assertEqual(final["room_miou_percent"], 50)
        self.assertEqual(stability[0]["room_miou_population_sd_pp"], 12.5)
        self.assertEqual(stability[0]["room_miou_worst_stage_percent"], 25)
        self.assertFalse(audit["paper_manifest_complete"])

    def test_f1_is_averaged_after_snapshot_computation(self):
        rows = [row("a", "a1", "20", .3, .5, 1), row("a", "a1", "final", .3, 1, .5)]
        summaries, _, _ = evaluation.aggregate(rows)
        average = next(r for r in summaries if r["stage"] == "average")
        self.assertAlmostEqual(average["f1_percent"], 200 / 3)
        self.assertEqual(average["precision_percent"], 75)
        self.assertEqual(average["recall_percent"], 75)

    def test_duplicate_snapshots_and_incorrect_f1_are_errors(self):
        sample = row("a", "a1", "final", .5)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            evaluation.aggregate([sample, sample])
        sample["f1"] = .9
        with self.assertRaisesRegex(ValueError, "F1"):
            evaluation.aggregate([sample])

    def test_final_is_not_assumed_to_be_full_coverage(self):
        with self.assertRaisesRegex(ValueError, "100% coverage"):
            evaluation.aggregate([row("a", "a1", "100", .5)])

    def test_complete_manuscript_counts_and_missing_baseline(self):
        rows = []
        counter = 0
        for dataset, count in (("interioragent", 15), ("grscene", 59)):
            for scene_index in range(count):
                for trajectory in range(5):
                    for stage in evaluation.STAGES:
                        if stage == "90" and counter < 22:
                            continue
                        sample = row(str(scene_index), str(trajectory), stage, 1)
                        sample["dataset"] = dataset
                        rows.append(sample)
                    counter += 1
        normalized = evaluation.normalize_rows(rows)
        self.assertTrue(evaluation.protocol_audit(normalized)["paper_manifest_complete"])
        baseline = [{**r, "method": "baseline"} for r in normalized[:-1]]
        report = evaluation.protocol_audit(normalized + baseline)
        self.assertFalse(report["paper_manifest_complete"])
        self.assertEqual(report["methods"]["baseline"]["missing_shared_snapshots"], 1)


if __name__ == "__main__":
    unittest.main()
