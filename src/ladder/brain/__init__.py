"""The trained brain: a small local network that picks Reflex's next action.

It reads numbers about the moment (features.py), predicts what each action leads to (net.py),
and a style weighs those predictions into a choice (policy.py). Every game it plays is logged
step by step (selfplay.py), turned into training rows (corpus.py) and trained on (train.py):
docs/trained-brain.md.
"""
