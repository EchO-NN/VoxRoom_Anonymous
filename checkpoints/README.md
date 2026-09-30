# Verifier checkpoint

The trained checkpoint is not included in this release. To train one, follow
[the training instructions](../docs/method.md#entry-seed-verifier-and-training)
with your scene manifest and candidate annotations.

The paper settings use 16 training scenes, 4 validation scenes, batch size 64,
AdamW at 0.0003, and positive-class weight 5.60. Select the checkpoint by
validation F1 at threshold 0.5.

Place the checkpoint at `checkpoints/entry_seed_verifier.pt`, or pass its path
with `--checkpoint`. For a geometry-only example, run replay with `--rules-only`.
