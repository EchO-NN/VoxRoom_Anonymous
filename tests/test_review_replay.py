import numpy as np
import pytest

from voxroom_online.review_replay import main, synthetic_snapshot


def test_review_prediction_keeps_structural_room_outside_navigation_domain(tmp_path):
    snapshot = synthetic_snapshot()
    snapshot["observed_free_mask"][10:20, 50:60] = False
    snapshot["unknown_mask"][10:20, 50:60] = True
    path = tmp_path / "observations.npz"
    np.savez_compressed(path, **snapshot)
    out = tmp_path / "out"
    assert main(["--snapshot", str(path), "--rules-only", "--output", str(out)]) == 0
    with np.load(out / "prediction_000000.npz", allow_pickle=False) as data:
        assert data["sfm_free"][12, 52]
        assert data["pred_labels"][12, 52] > 0
        assert data["navigation_labels"][12, 52] == 0
        assert np.unique(data["pred_labels"][data["pred_labels"] > 0]).size == 2


def test_full_method_does_not_silently_accept_missing_checkpoint(tmp_path):
    with pytest.raises(SystemExit) as failure:
        main(["--demo", "--checkpoint", str(tmp_path / "absent.pt"), "--output", str(tmp_path / "out")])
    assert failure.value.code == 2
    assert not (tmp_path / "out").exists()
