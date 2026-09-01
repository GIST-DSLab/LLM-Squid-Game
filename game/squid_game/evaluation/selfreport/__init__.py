"""Self-report channel -- what the model says about its own decision.

Two instruments. ``reason_convergence`` reads the REASON digit emitted with
a forfeit/continue choice and asks whether it converges with the framing
manipulation. ``psuccess`` (Task 5) reads the model's own success estimate
and the expected value it implies.

This channel is deliberately separate from ``cognitive/``: a model whose
thinking tokens rise while its stated reason does not move is the
dissociation the study is looking for, and it is unmeasurable if the two
are estimated in one file.
"""
