"""SentenceBERT embeddings + linear probe over per-turn reasoning traces.

Question
--------
Is a turn's *outcome class* linearly decodable from the agent's own
chain of thought?  Two label sets are supported:

``forfeit``
    FORFEIT vs CONTINUE, restricted to ``forfeit_condition == allowed``
    (the only cells where FORFEIT is reachable).  This is the behavioural
    stand-in for "the turn the agent ended".  Note the canonical
    2026-04-22 runs were executed in **phantom-death mode**
    (``engine.py`` passes ``phantom_death=not task_cfg.actual_death``), so
    ``died`` is False on all 8 255 turns and cannot be a label.

``threat``
    ``flagship_corruption`` vs ``baseline_flagship`` — did the Push
    framing leave a linearly readable trace?  ``true_baseline`` is
    dropped so that the two arms match on ``p_end`` and call cascade.

Guardrails
----------
*Session-grouped CV.*  ``GroupKFold`` on ``session_id``: turns from one
session never straddle the train/test split.  Without this, a probe can
memorise a session's stylistic fingerprint and score far above its true
generalisation.

*Scalar baseline.*  A probe fit on ``(turn_number, score_before_turn,
ri_task, psuccess_self)`` alone.  FORFEIT turns cluster late in a
session, so the embedding must beat this baseline to have shown anything
about the *content* of the reasoning.

*Permutation null.*  Labels are shuffled **between whole sessions**, which
preserves the within-session label structure that grouped CV exploits.
The reported p-value is the fraction of permuted runs reaching the
observed AUROC.

*Leakage masking.*  See ``scripts/probe_lexicon.py``.  Every probe is fit
raw and masked.

Usage
-----
    uv run python -m scripts.probe_reasoning_embeddings \
        --label forfeit --label threat \
        --channel task \
        --out outputs/reasoning_probe
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from scripts._ri_dataset import load_all
from scripts.probe_lexicon import build_masker, mask_text

DEFAULT_SBERT = "sentence-transformers/all-MiniLM-L6-v2"
SCALAR_FEATURES = (
    "turn_number",
    "score_before_turn",
    "ri_task",
    "psuccess_self",
)


@dataclass(frozen=True)
class LabelSpec:
    """How one binary label is carved out of the turn table."""

    name: str
    positive: str
    negative: str

    def apply(self, frame: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
        raise NotImplementedError


class ForfeitLabel(LabelSpec):
    def apply(self, frame):
        sub = frame[frame["forfeit_allowed"]].copy()
        return sub, sub["forfeit"].to_numpy(dtype=int)


class ThreatLabel(LabelSpec):
    def apply(self, frame):
        sub = frame[
            frame["framing"].isin(
                ["flagship_corruption", "baseline_flagship"]
            )
        ].copy()
        return sub, (sub["framing"] == "flagship_corruption").to_numpy(int)


LABELS: dict[str, LabelSpec] = {
    "forfeit": ForfeitLabel(
        "forfeit", "FORFEIT", "CONTINUE (forfeit-allowed cells only)"
    ),
    "threat": ThreatLabel(
        "threat", "flagship_corruption", "baseline_flagship"
    ),
}


# --------------------------------------------------------------------
# Embedding
# --------------------------------------------------------------------
def _chunks(text: str, words_per_chunk: int) -> list[str]:
    """Split a long trace into fixed-word chunks.

    MiniLM truncates at 256 word-pieces but these traces run 200-3 000
    tokens, so encoding the raw string would silently discard most of the
    reasoning.  Chunk-then-mean-pool keeps the whole trace in the vector
    at the cost of losing long-range order — acceptable for a bag-of-
    meaning probe.
    """
    words = text.split()
    if not words:
        return [""]
    return [
        " ".join(words[i : i + words_per_chunk])
        for i in range(0, len(words), words_per_chunk)
    ]


def embed_texts(
    texts: list[str],
    *,
    sbert_model: str,
    words_per_chunk: int,
    batch_size: int,
    cache_dir: Path,
    cache_tag: str,
) -> np.ndarray:
    """Chunked mean-pooled SentenceBERT embeddings, disk-cached.

    The cache key folds in the model name and the exact text contents, so
    a changed mask set or a changed SBERT checkpoint misses the cache
    rather than silently reusing stale vectors.
    """
    digest = hashlib.sha256(
        ("\x00".join(texts) + sbert_model + str(words_per_chunk)).encode()
    ).hexdigest()[:16]
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{cache_tag}__{digest}.npy"
    if cache_path.exists():
        return np.load(cache_path)

    from sentence_transformers import SentenceTransformer

    encoder = SentenceTransformer(sbert_model)
    flat: list[str] = []
    spans: list[tuple[int, int]] = []
    for text in texts:
        pieces = _chunks(text, words_per_chunk)
        spans.append((len(flat), len(flat) + len(pieces)))
        flat.extend(pieces)

    raw = encoder.encode(
        flat,
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    pooled = np.stack([raw[start:stop].mean(axis=0) for start, stop in spans])
    norms = np.linalg.norm(pooled, axis=1, keepdims=True)
    pooled = pooled / np.where(norms == 0, 1.0, norms)
    np.save(cache_path, pooled)
    return pooled


# --------------------------------------------------------------------
# Probe
# --------------------------------------------------------------------
def _fit_cv(
    features: np.ndarray,
    labels: np.ndarray,
    groups: np.ndarray,
    *,
    n_splits: int,
    seed: int,
) -> dict:
    """Session-grouped CV logistic probe; returns out-of-fold scores."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score, roc_auc_score
    from sklearn.model_selection import GroupKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    oof = np.full(len(labels), np.nan)
    fold_auc: list[float] = []
    coefs: list[np.ndarray] = []
    splitter = GroupKFold(n_splits=n_splits)
    for train_idx, test_idx in splitter.split(features, labels, groups):
        if len(np.unique(labels[train_idx])) < 2:
            continue
        pipeline = make_pipeline(
            StandardScaler(),
            LogisticRegression(
                max_iter=5000,
                C=1.0,
                class_weight="balanced",
                random_state=seed,
            ),
        )
        pipeline.fit(features[train_idx], labels[train_idx])
        scores = pipeline.decision_function(features[test_idx])
        oof[test_idx] = scores
        if len(np.unique(labels[test_idx])) == 2:
            fold_auc.append(roc_auc_score(labels[test_idx], scores))
        coefs.append(pipeline[-1].coef_.ravel())

    valid = ~np.isnan(oof)
    pooled_auc = (
        float(roc_auc_score(labels[valid], oof[valid]))
        if len(np.unique(labels[valid])) == 2
        else float("nan")
    )
    return {
        "auroc_oof": pooled_auc,
        "auroc_fold_mean": float(np.mean(fold_auc)) if fold_auc else float("nan"),
        "auroc_fold_sd": float(np.std(fold_auc)) if fold_auc else float("nan"),
        "average_precision": float(
            average_precision_score(labels[valid], oof[valid])
        ),
        "n": int(len(labels)),
        "n_positive": int(labels.sum()),
        "prevalence": float(labels.mean()),
        "n_sessions": int(len(np.unique(groups))),
        "_oof": oof,
        "_coef": np.mean(coefs, axis=0) if coefs else None,
    }


def _permutation_worker(
    features: np.ndarray,
    shuffled: np.ndarray,
    groups: np.ndarray,
    n_splits: int,
    seed: int,
) -> float:
    """One permuted CV fit. Module-level so joblib can pickle it."""
    return _fit_cv(
        features, shuffled, groups, n_splits=n_splits, seed=seed
    )["auroc_oof"]


def _permutation_null(
    features: np.ndarray,
    labels: np.ndarray,
    groups: np.ndarray,
    observed: float,
    *,
    n_perm: int,
    n_splits: int,
    seed: int,
) -> dict:
    """Session-level label shuffle.

    Labels move as whole sessions so that the permuted data keeps the
    same within-session correlation the real data has; a turn-level
    shuffle would destroy it and make the null far too easy to beat.
    """
    from joblib import Parallel, delayed

    rng = np.random.default_rng(seed)
    frame = pd.DataFrame({"g": groups, "y": labels})
    session_labels = frame.groupby("g")["y"].agg(list)
    session_ids = session_labels.index.to_numpy()
    donor = {sid: list(session_labels[sid]) for sid in session_ids}

    def _draw() -> np.ndarray | None:
        """One session-level relabelling.

        Each session borrows the label sequence of a randomly matched
        donor session, cycling if the donor is shorter. Sessions differ
        in length (a forfeit truncates one early), so a positional copy
        would silently drop the tail of the longer ones.
        """
        mapping = dict(zip(session_ids, rng.permutation(session_ids)))
        shuffled = np.empty_like(labels)
        cursor: dict = {sid: 0 for sid in session_ids}
        for i, g in enumerate(groups):
            src = mapping[g]
            pool = donor[src]
            shuffled[i] = pool[cursor[src] % len(pool)]
            cursor[src] += 1
        return shuffled if len(np.unique(shuffled)) > 1 else None

    draws = [d for d in (_draw() for _ in range(n_perm)) if d is not None]
    # The draws are generated serially (the RNG is stateful) but the CV
    # fits, which dominate the cost, run in parallel.
    null_scores = Parallel(n_jobs=-1, prefer="processes")(
        delayed(_permutation_worker)(features, d, groups, n_splits, seed)
        for d in draws
    )

    null_array = np.array([s for s in null_scores if np.isfinite(s)])
    if null_array.size == 0:
        return {"p_value": float("nan"), "null_mean": float("nan")}
    return {
        "n_permutations": int(null_array.size),
        "null_mean": float(null_array.mean()),
        "null_sd": float(null_array.std()),
        "null_p95": float(np.percentile(null_array, 95)),
        "p_value": float(
            (np.sum(null_array >= observed) + 1) / (null_array.size + 1)
        ),
    }


def _scalar_matrix(frame: pd.DataFrame) -> np.ndarray:
    cols = [c for c in SCALAR_FEATURES if c in frame.columns]
    matrix = frame[cols].astype(float)
    return matrix.fillna(matrix.median()).to_numpy()


def build_embedding_bank(
    frame: pd.DataFrame,
    *,
    channels: list[str],
    mask_sets: list[str],
    args,
) -> dict[tuple[str, str], np.ndarray]:
    """Encode every turn once, keyed by ``(channel, variant)``.

    Encoding is the expensive step, and the two label sets overlap almost
    entirely (`forfeit` uses Cells 1/3/5, `threat` uses Cells 1-4).
    Encoding per label subset would re-embed the shared rows and, because
    the disk cache is keyed on the exact text list, would also miss the
    cache every time.  So the bank is built over the *whole* frame in
    frame-row order and each probe slices it by positional index.
    """
    bank: dict[tuple[str, str], np.ndarray] = {}
    masker = build_masker(mask_sets) if mask_sets else None
    mask_tag = "-".join(sorted(mask_sets)) if mask_sets else "none"
    for channel in channels:
        raw_texts = frame[f"text_{channel}"].fillna("").tolist()
        bank[(channel, "embedding_raw")] = embed_texts(
            raw_texts,
            sbert_model=args.sbert_model,
            words_per_chunk=args.words_per_chunk,
            batch_size=args.batch_size,
            cache_dir=args.out / "_embedding_cache",
            cache_tag=f"all__{channel}__raw",
        )
        if masker is not None:
            bank[(channel, "embedding_masked")] = embed_texts(
                [mask_text(t, masker) for t in raw_texts],
                sbert_model=args.sbert_model,
                words_per_chunk=args.words_per_chunk,
                batch_size=args.batch_size,
                cache_dir=args.out / "_embedding_cache",
                cache_tag=f"all__{channel}__masked-{mask_tag}",
            )
    return bank


def run_cell(
    frame: pd.DataFrame,
    bank: dict[tuple[str, str], np.ndarray],
    *,
    label_name: str,
    channel: str,
    group_label: str,
    args,
) -> dict | None:
    """Fit every probe variant for one (group, label, channel) cell.

    ``frame`` must carry a ``bank_row`` column giving each row's position
    in the embedding bank.
    """
    sub, _ = LABELS[label_name].apply(frame)
    text_column = f"text_{channel}"
    sub = sub[sub[text_column].fillna("").str.strip().str.len() > 0]
    if sub.empty:
        return {
            "status": "skipped",
            "reason": f"no non-empty {text_column}",
            "label": label_name,
            "channel": channel,
            "model": group_label,
            "n": 0,
        }
    sub, labels = LABELS[label_name].apply(sub)
    if len(np.unique(labels)) < 2 or labels.sum() < args.min_positive:
        return {
            "status": "skipped",
            "reason": f"positives={int(labels.sum())} "
            f"< min_positive={args.min_positive}",
            "label": label_name,
            "channel": channel,
            "model": group_label,
            "n": int(len(sub)),
        }

    rows = sub["bank_row"].to_numpy()
    groups = sub["session_id"].to_numpy()
    out: dict = {
        "status": "ok",
        "model": group_label,
        "label": label_name,
        "channel": channel,
        "positive_class": LABELS[label_name].positive,
        "negative_class": LABELS[label_name].negative,
    }

    variants: dict[str, np.ndarray] = {
        name: matrix[rows]
        for (bank_channel, name), matrix in bank.items()
        if bank_channel == channel
    }
    variants["scalar_baseline"] = _scalar_matrix(sub)

    results: dict[str, dict] = {}
    for variant_name in sorted(variants):
        matrix = variants[variant_name]
        fit = _fit_cv(
            matrix, labels, groups, n_splits=args.n_splits, seed=args.seed
        )
        coef = fit.pop("_coef")
        oof = fit.pop("_oof")
        if variant_name == "embedding_raw" and args.exemplars:
            fit["exemplars"] = _exemplars(sub, oof, labels, args.exemplars)
        if variant_name.startswith("embedding") and args.n_permutations:
            fit["permutation_null"] = _permutation_null(
                matrix,
                labels,
                groups,
                fit["auroc_oof"],
                n_perm=args.n_permutations,
                n_splits=args.n_splits,
                seed=args.seed,
            )
        if coef is not None:
            fit["coef_l2_norm"] = float(np.linalg.norm(coef))
        results[variant_name] = fit
    out["variants"] = results
    return out


def _exemplars(
    frame: pd.DataFrame, oof: np.ndarray, labels: np.ndarray, k: int
) -> dict:
    """Most- and least-positive out-of-fold turns, for eyeballing."""
    order = np.argsort(np.where(np.isnan(oof), -np.inf, oof))
    def snap(index_array):
        return [
            {
                "session_id": frame["session_id"].iloc[i],
                "turn": int(frame["turn_number"].iloc[i]),
                "label": int(labels[i]),
                "score": float(oof[i]),
                "framing": frame["framing"].iloc[i],
            }
            for i in index_array
        ]
    return {"top": snap(order[::-1][:k]), "bottom": snap(order[:k])}


# --------------------------------------------------------------------
def render_report(results: list[dict]) -> str:
    lines = [
        "# Reasoning-trace linear probe",
        "",
        "SentenceBERT embedding of the per-turn thinking trace ->"
        " L2 logistic probe, session-grouped 5-fold CV.",
        "",
        "`scalar_baseline` = probe on (turn, score, ri_task, psuccess_self)"
        " only. The embedding must beat it to have read the *content*.",
        "`embedding_masked` = surface framing vocabulary removed"
        " (see `scripts/probe_lexicon.py`).",
        "`null` = session-level label-shuffle AUROC mean;"
        " `p` = permutation p-value.",
        "",
        "| label | channel | model | n | pos | variant | AUROC (oof) |"
        " fold mean ± sd | AP | null | p |",
        "|---|---|---|---:|---:|---|---:|---|---:|---:|---:|",
    ]
    for cell in results:
        if cell is None or cell.get("status") != "ok":
            continue
        for variant, fit in cell["variants"].items():
            null = fit.get("permutation_null", {})
            lines.append(
                f"| {cell['label']} | {cell['channel']} | {cell['model']} | "
                f"{fit['n']} | {fit['n_positive']} | {variant} | "
                f"{fit['auroc_oof']:.3f} | "
                f"{fit['auroc_fold_mean']:.3f} ± {fit['auroc_fold_sd']:.3f} | "
                f"{fit['average_precision']:.3f} | "
                f"{null.get('null_mean', float('nan')):.3f} | "
                f"{null.get('p_value', float('nan')):.4f} |"
            )
    skipped = [c for c in results if c and c.get("status") == "skipped"]
    if skipped:
        lines += ["", "## Skipped cells", ""]
        lines += [f"- {c['reason']} (n={c['n']})" for c in skipped]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("outputs/final_results"))
    parser.add_argument("--out", type=Path, default=Path("outputs/reasoning_probe"))
    parser.add_argument(
        "--label", action="append", choices=sorted(LABELS), dest="labels"
    )
    parser.add_argument(
        "--channel", action="append", choices=["task", "probe", "forfeit"],
        dest="channels",
    )
    parser.add_argument(
        "--mask", action="append", choices=["threat", "pull", "decision"],
        dest="mask_sets", default=None,
    )
    parser.add_argument("--model", action="append", dest="models")
    parser.add_argument("--sbert-model", default=DEFAULT_SBERT)
    parser.add_argument("--words-per-chunk", type=int, default=180)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--n-permutations", type=int, default=100)
    parser.add_argument("--min-positive", type=int, default=20)
    parser.add_argument("--exemplars", type=int, default=5)
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument(
        "--per-model", action="store_true",
        help="Additionally fit one probe per model, not just pooled.",
    )
    args = parser.parse_args()
    args.labels = args.labels or ["forfeit", "threat"]
    args.channels = args.channels or ["task"]
    mask_sets = args.mask_sets if args.mask_sets is not None else ["threat", "pull"]

    frame = load_all(args.root, include_text=True, models=args.models)
    frame["bank_row"] = np.arange(len(frame))
    args.out.mkdir(parents=True, exist_ok=True)
    bank = build_embedding_bank(
        frame, channels=args.channels, mask_sets=mask_sets, args=args
    )

    groupings: list[tuple[str, pd.DataFrame]] = [("POOLED", frame)]
    if args.per_model:
        groupings += [
            (m, frame[frame["model"] == m])
            for m in sorted(frame["model"].unique())
        ]

    results: list[dict] = []
    for group_label, group in groupings:
        for label_name in args.labels:
            for channel in args.channels:
                results.append(
                    run_cell(
                        group,
                        bank,
                        label_name=label_name,
                        channel=channel,
                        group_label=group_label,
                        args=args,
                    )
                )

    (args.out / "probe_results.json").write_text(
        json.dumps([r for r in results if r], indent=2, default=str)
    )
    report = render_report(results)
    (args.out / "probe_report.md").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
