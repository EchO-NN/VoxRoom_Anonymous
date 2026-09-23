# Learned verifier checkpoints

Train the verifier on the disjoint 16-scene training
and 4-scene validation split, with batch size 64, AdamW learning rate 0.0003,
positive-class weight 5.60, and selection by validation F1 at threshold 0.5.

Train using the provided training configuration and place the resulting checkpoint
at `checkpoints/entry_seed_verifier.pt`, or pass `--checkpoint` to replay. Runtime
checks validate the architecture and input semantics. Missing weights are an error;
the explicitly named `--rules-only` option is a diagnostic ablation only.
