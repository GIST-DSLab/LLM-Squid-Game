"""SentenceBERT embeddings + linear probe over per-turn reasoning traces.

Question
--------
Is a turn's *outcome class* — or the *threat level it was run under* —
linearly decodable from the agent's own chain of thought?  Three targets
are supported; ``threat_level`` is the default (P1, spec §5.2) and is a
**regression**, the other two are the older binary classifications.

``threat_level``
    Ordinal 0-3 (``true_baseline`` → 0, ``threat_l1/2/3`` → 1/2/3; with
    ``legacy=True`` the archived v6 framings map through
    :data:`~squid_game.evaluation.shared.threat_level.LEGACY_THREAT_LEVEL`).
    Scored by out-of-fold R², Spearman ρ and MAE rather than AUROC: the
    ladder is ordered, and a probe that recovers the *order* is making a
    stronger claim than one that separates two arbitrary arms.

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
ri_<channel>, lives_remaining)`` alone.  FORFEIT turns cluster late in a
session, so the embedding must beat this baseline to have shown anything
about the *content* of the reasoning.  ``scalar_plus_embedding``
concatenates the two, answering the follow-up question the baseline
raises: does the text add anything *on top of* the scalars?

Missing scalars are filled with ``-1`` (a value outside every feature's
natural range), not with the column median: a median computed over the
whole cell would carry test-fold information into the training folds.

*Permutation null.*  Labels are shuffled **between whole sessions**, which
preserves the within-session label structure that grouped CV exploits.
The reported p-value is the fraction of permuted runs reaching the
observed AUROC.

*Leakage masking.*  See ``squid_game.evaluation.semantic.lexicon``.  Every
probe is fit raw and masked.

The model, its embedding pipeline, and its report rendering live here;
orchestration (argparse, the channel/label variant loop, disk I/O) is the
caller's responsibility -- see ``scripts/analysis/probe_reasoning_embeddings.py``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from squid_game.evaluation.semantic.lexicon import build_masker, mask_text

DEFAULT_SBERT = "sentence-transformers/all-MiniLM-L6-v2"

#: Mask sets applied by default. ``decision`` is in the default set because
#: without it the ``forfeit`` target on the ``forfeit`` channel is scored on
#: text containing the literal word "FORFEIT" — an AUROC of 0.985 that
#: measures nothing but the probe's ability to read its own label back.
#: ``lives`` is in it for the same reason on ``threat_level``.
DEFAULT_MASK_SETS: tuple[str, ...] = ("threat", "pull", "decision", "lives")

#: Channel-independent half of the scalar baseline. The channel's own
#: reasoning-investment column (``ri_task`` / ``ri_probe`` / ``ri_forfeit``)
#: is appended per cell by :func:`_scalar_matrix`.
SCALAR_FEATURES = (
    "turn_number",
    "score_before_turn",
    "lives_remaining",
)

#: Filled in for any scalar the trace does not carry (``lives_remaining`` on
#: every pre-2026-09-03 run). Outside the natural range of all four columns.
SCALAR_FILL = -1.0

RIDGE_ALPHAS = np.logspace(-2, 3, 12)


@dataclass(frozen=True)
class LabelSpec:
    """How one target is carved out of the turn table.

    ``kind`` selects the estimator: ``classification`` fits the L2 logistic
    probe scored by AUROC, ``regression`` fits the RidgeCV probe scored by
    R²/ρ/MAE. ``positive``/``negative`` are display strings; for a
    regression they describe the two ends of the scale.
    """

    name: str
    positive: str
    negative: str
    kind: str = "classification"

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


class ThreatLevelTarget(LabelSpec):
    """Ordinal threat level (P1). Rows whose framing has no level are dropped.

    ``threat_level`` is written by
    :func:`squid_game.evaluation.semantic.dataset.load_turns`, which resolves
    it through the shared mapping and honours ``--legacy-mapping``. An
    unmapped framing yields NaN here rather than 0, so an archived
    ``baseline_flagship`` run analysed *without* ``--legacy-mapping``
    contributes no rows at all instead of silently posing as neutral.
    """

    def apply(self, frame):
        if "threat_level" not in frame.columns:
            return frame.iloc[0:0].copy(), np.empty(0, dtype=float)
        sub = frame[frame["threat_level"].notna()].copy()
        return sub, sub["threat_level"].to_numpy(dtype=float)


LABELS: dict[str, LabelSpec] = {
    "forfeit": ForfeitLabel(
        "forfeit", "FORFEIT", "CONTINUE (forfeit-allowed cells only)"
    ),
    "threat": ThreatLabel(
        "threat", "flagship_corruption", "baseline_flagship"
    ),
    "threat_level": ThreatLevelTarget(
        "threat_level", "level 3", "level 0", kind="regression"
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
def _shuffle_groups(groups: np.ndarray, seed: int) -> np.ndarray:
    """Relabel sessions in a seeded random order before ``GroupKFold``.

    ``GroupKFold`` takes no ``random_state``: it packs groups into folds by
    descending size, so with the many equal-length sessions this design
    produces, the fold assignment is fixed by the session's *name*. Renaming
    the sessions to a seeded permutation makes the split depend on ``seed``
    while keeping the guarantee that matters — no session straddles a split.
    """
    uniq = pd.unique(pd.Series(groups))
    order = np.random.default_rng(seed).permutation(len(uniq))
    mapping = {group: int(order[i]) for i, group in enumerate(uniq)}
    return np.array([mapping[g] for g in groups])


def _effective_splits(n_splits: int, groups: np.ndarray) -> int:
    return max(2, min(n_splits, int(len(np.unique(groups)))))


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
    fold_groups = _shuffle_groups(groups, seed)
    splitter = GroupKFold(n_splits=_effective_splits(n_splits, fold_groups))
    for train_idx, test_idx in splitter.split(features, labels, fold_groups):
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


def fit_regression_cv(
    features: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    *,
    n_splits: int = 5,
    seed: int = 1234,
) -> dict:
    """Session-grouped CV ridge probe on an ordinal target (P1).

    ``RidgeCV`` picks its own penalty by leave-one-out GCV *inside each
    training fold*, so the regularisation strength is never chosen with
    sight of the held-out sessions. Reported metrics are pooled
    out-of-fold: R² (variance of the level explained), Spearman ρ (does the
    probe recover the ladder's *order*) and MAE (in levels).
    """
    from scipy.stats import spearmanr
    from sklearn.linear_model import RidgeCV
    from sklearn.metrics import mean_absolute_error, r2_score
    from sklearn.model_selection import GroupKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    y = np.asarray(y, dtype=float)
    oof = np.full(len(y), np.nan)
    alphas: list[float] = []
    coefs: list[np.ndarray] = []
    fold_groups = _shuffle_groups(groups, seed)
    splitter = GroupKFold(n_splits=_effective_splits(n_splits, fold_groups))
    for train_idx, test_idx in splitter.split(features, y, fold_groups):
        if np.unique(y[train_idx]).size < 2:
            continue
        pipeline = make_pipeline(
            StandardScaler(), RidgeCV(alphas=RIDGE_ALPHAS)
        )
        pipeline.fit(features[train_idx], y[train_idx])
        oof[test_idx] = pipeline.predict(features[test_idx])
        alphas.append(float(pipeline[-1].alpha_))
        coefs.append(np.asarray(pipeline[-1].coef_).ravel())

    valid = ~np.isnan(oof)
    if valid.sum() < 2 or np.unique(y[valid]).size < 2:
        nan = float("nan")
        return {
            "r2": nan, "spearman": nan, "mae": nan, "alpha": nan,
            "n": int(len(y)), "n_sessions": int(len(np.unique(groups))),
            "n_levels": int(np.unique(y).size), "_oof": oof, "_coef": None,
        }
    rho = spearmanr(y[valid], oof[valid]).statistic
    return {
        "r2": float(r2_score(y[valid], oof[valid])),
        "spearman": float(rho) if np.isfinite(rho) else float("nan"),
        "mae": float(mean_absolute_error(y[valid], oof[valid])),
        "alpha": float(np.mean(alphas)) if alphas else float("nan"),
        "n": int(len(y)),
        "n_sessions": int(len(np.unique(groups))),
        "n_levels": int(np.unique(y).size),
        "level_mean": float(np.mean(y)),
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
    """One permuted classification fit. Module-level so joblib can pickle it."""
    return _fit_cv(
        features, shuffled, groups, n_splits=n_splits, seed=seed
    )["auroc_oof"]


def _permutation_worker_regression(
    features: np.ndarray,
    shuffled: np.ndarray,
    groups: np.ndarray,
    n_splits: int,
    seed: int,
) -> tuple[float, float]:
    fit = fit_regression_cv(
        features, shuffled, groups, n_splits=n_splits, seed=seed
    )
    return fit["r2"], fit["spearman"]


#: Statistic names carried in the null for each estimator kind, in the order
#: the workers return them.
_NULL_STATS: dict[str, tuple[str, ...]] = {
    "classification": ("auroc_oof",),
    "regression": ("r2", "spearman"),
}

# A degenerate draw (every session handed the same label) carries no
# information, so it is redrawn rather than dropped -- dropping is what made
# the reported ``n_permutations`` silently smaller than the requested count.
_MAX_DRAW_ATTEMPTS_PER_PERM = 20


def _permutation_null(
    features: np.ndarray,
    labels: np.ndarray,
    groups: np.ndarray,
    observed: dict[str, float],
    *,
    n_perm: int,
    n_splits: int,
    seed: int,
    kind: str = "classification",
) -> dict:
    """Session-level label shuffle.

    Labels move as whole sessions so that the permuted data keeps the
    same within-session correlation the real data has; a turn-level
    shuffle would destroy it and make the null far too easy to beat.

    Each draw is fit under its own seed (``seed + draw_index``), so the null
    absorbs the fold-assignment variability that the single observed fit
    also carries. Reusing one seed for every draw — the previous behaviour —
    held the split fixed across the whole null and made the resulting
    p-value an understatement of the true sampling variability.
    """
    from joblib import Parallel, delayed

    stats = _NULL_STATS[kind]
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

    draws: list[np.ndarray] = []
    attempts = 0
    while len(draws) < n_perm and attempts < n_perm * _MAX_DRAW_ATTEMPTS_PER_PERM:
        attempts += 1
        drawn = _draw()
        if drawn is not None:
            draws.append(drawn)
    if not draws:
        return {
            "n_permutations_requested": int(n_perm),
            "n_permutations": 0,
            "p_value": float("nan"),
            "null_mean": float("nan"),
        }

    worker = (
        _permutation_worker_regression
        if kind == "regression"
        else _permutation_worker
    )
    # The draws are generated serially (the RNG is stateful) but the CV
    # fits, which dominate the cost, run in parallel.
    raw = Parallel(n_jobs=-1, prefer="processes")(
        delayed(worker)(features, d, groups, n_splits, seed + i)
        for i, d in enumerate(draws)
    )
    columns = np.atleast_2d(np.asarray(raw, dtype=float).T)

    out: dict = {
        "n_permutations_requested": int(n_perm),
        "n_permutations": int(len(draws)),
    }
    for position, stat in enumerate(stats):
        values = columns[position]
        values = values[np.isfinite(values)]
        prefix = "" if len(stats) == 1 else f"{stat}_"
        if values.size == 0:
            out[f"{prefix}p_value"] = float("nan")
            out[f"{prefix}null_mean"] = float("nan")
            continue
        obs = float(observed.get(stat, float("nan")))
        out[f"{prefix}null_mean"] = float(values.mean())
        out[f"{prefix}null_sd"] = float(values.std())
        out[f"{prefix}null_p95"] = float(np.percentile(values, 95))
        out[f"{prefix}p_value"] = (
            float((np.sum(values >= obs) + 1) / (values.size + 1))
            if np.isfinite(obs)
            else float("nan")
        )
    if len(stats) > 1:
        # The headline p is the first statistic's, so every caller can read
        # ``permutation_null["p_value"]`` regardless of estimator kind.
        out["p_value"] = out[f"{stats[0]}_p_value"]
        out["null_mean"] = out[f"{stats[0]}_null_mean"]
        out["n_permutations_effective"] = int(
            np.isfinite(columns[0]).sum()
        )
    else:
        out["n_permutations_effective"] = int(np.isfinite(columns[0]).sum())
    return out


def _scalar_matrix(frame: pd.DataFrame, channel: str) -> np.ndarray:
    """The scalar baseline for one channel: turn, score, ri_<channel>, lives.

    Missing columns are materialised as :data:`SCALAR_FILL` so the feature
    count is identical across cells and models — otherwise an archived run
    (no ``lives_remaining``) and a ladder run would silently be compared on
    differently shaped baselines.
    """
    cols = [*SCALAR_FEATURES, f"ri_{channel}"]
    matrix = pd.DataFrame(index=frame.index)
    for col in cols:
        matrix[col] = (
            pd.to_numeric(frame[col], errors="coerce")
            if col in frame.columns
            else np.nan
        )
    return matrix.astype(float).fillna(SCALAR_FILL).to_numpy()


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

    The target's ``apply`` runs **once**, on a frame already narrowed to
    non-empty traces. It used to run twice (once before the text filter and
    once after) — harmless for the idempotent label specs, but it meant the
    reported ``n`` and the fitted rows came from different passes, and it
    doubled the cost of any future non-idempotent target.
    """
    spec = LABELS[label_name]
    text_column = f"text_{channel}"
    frame = frame[frame[text_column].fillna("").str.strip().str.len() > 0]
    if frame.empty:
        return {
            "status": "skipped",
            "reason": f"no non-empty {text_column}",
            "label": label_name,
            "channel": channel,
            "model": group_label,
            "n": 0,
        }
    sub, labels = spec.apply(frame)
    skip = _insufficient(sub, labels, spec, args)
    if skip is not None:
        return {
            "status": "skipped",
            "reason": skip,
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
        "kind": spec.kind,
        "channel": channel,
        "positive_class": spec.positive,
        "negative_class": spec.negative,
    }

    variants: dict[str, np.ndarray] = {
        name: matrix[rows]
        for (bank_channel, name), matrix in bank.items()
        if bank_channel == channel
    }
    scalars = _scalar_matrix(sub, channel)
    variants["scalar_baseline"] = scalars
    # "Does the text add anything the scalars did not already carry?" — the
    # question the scalar baseline raises but cannot answer on its own.
    if "embedding_raw" in variants:
        variants["scalar_plus_embedding"] = np.hstack(
            [scalars, variants["embedding_raw"]]
        )

    headline = "r2" if spec.kind == "regression" else "auroc_oof"
    results: dict[str, dict] = {}
    for variant_name in sorted(variants):
        matrix = variants[variant_name]
        if spec.kind == "regression":
            fit = fit_regression_cv(
                matrix, labels, groups, n_splits=args.n_splits, seed=args.seed
            )
        else:
            fit = _fit_cv(
                matrix, labels, groups, n_splits=args.n_splits, seed=args.seed
            )
        coef = fit.pop("_coef")
        oof = fit.pop("_oof")
        if variant_name == "embedding_raw" and getattr(args, "exemplars", 0):
            fit["exemplars"] = _exemplars(sub, oof, labels, args.exemplars)
        if variant_name != "scalar_baseline" and args.n_permutations:
            fit["permutation_null"] = _permutation_null(
                matrix,
                labels,
                groups,
                {k: fit[k] for k in _NULL_STATS[spec.kind]},
                n_perm=args.n_permutations,
                n_splits=args.n_splits,
                seed=args.seed,
                kind=spec.kind,
            )
        if coef is not None:
            fit["coef_l2_norm"] = float(np.linalg.norm(coef))
        fit["headline_metric"] = headline
        results[variant_name] = fit
    out["variants"] = results
    return out


def _insufficient(
    sub: pd.DataFrame, labels: np.ndarray, spec: LabelSpec, args
) -> str | None:
    """Why this cell cannot be fit, or ``None`` when it can."""
    n_sessions = int(sub["session_id"].nunique()) if len(sub) else 0
    if np.unique(labels).size < 2:
        return f"only {np.unique(labels).size} distinct target value(s)"
    if n_sessions < args.n_splits:
        return f"sessions={n_sessions} < n_splits={args.n_splits}"
    if spec.kind == "regression":
        min_rows = getattr(args, "min_rows", 0) or args.n_splits * 10
        if len(sub) < min_rows:
            return f"rows={len(sub)} < min_rows={min_rows}"
        return None
    if labels.sum() < args.min_positive:
        return (
            f"positives={int(labels.sum())} "
            f"< min_positive={args.min_positive}"
        )
    return None


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
                "label": float(labels[i]),
                "score": float(oof[i]),
                "framing": frame["framing"].iloc[i],
            }
            for i in index_array
        ]
    return {"top": snap(order[::-1][:k]), "bottom": snap(order[:k])}


# --------------------------------------------------------------------
_PREAMBLE = [
    "# Reasoning-trace linear probe",
    "",
    "SentenceBERT embedding of the per-turn thinking trace -> linear probe,"
    " session-grouped k-fold CV (fold assignment seeded).",
    "",
    "`scalar_baseline` = probe on (turn, score, ri_<channel>,"
    " lives_remaining) only. The embedding must beat it to have read the"
    " *content*. `scalar_plus_embedding` = both, concatenated.",
    "`embedding_masked` = surface framing/decision/lives vocabulary removed"
    " (`squid_game.evaluation.semantic.lexicon`).",
    "`null` = session-level label-shuffle mean; `p` = permutation p-value"
    " (each draw fit under its own seed).",
    "",
]


def _regression_rows(results: list[dict]) -> list[str]:
    lines = [
        "## Regression targets (R² / Spearman ρ / MAE)",
        "",
        "| target | channel | model | n | sessions | variant | R² (oof) |"
        " ρ | MAE | null R² | p(R²) | p(ρ) |",
        "|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for cell in results:
        if cell is None or cell.get("status") != "ok":
            continue
        if cell.get("kind") != "regression":
            continue
        for variant, fit in cell["variants"].items():
            null = fit.get("permutation_null", {})
            lines.append(
                f"| {cell['label']} | {cell['channel']} | {cell['model']} | "
                f"{fit['n']} | {fit['n_sessions']} | {variant} | "
                f"{fit['r2']:.3f} | {fit['spearman']:.3f} | "
                f"{fit['mae']:.3f} | "
                f"{null.get('r2_null_mean', float('nan')):.3f} | "
                f"{null.get('r2_p_value', float('nan')):.4f} | "
                f"{null.get('spearman_p_value', float('nan')):.4f} |"
            )
    # 4 = the header lines alone; nothing of this kind was fit.
    return lines if len(lines) > 4 else []


def _classification_rows(results: list[dict]) -> list[str]:
    lines = [
        "## Classification targets (AUROC)",
        "",
        "| label | channel | model | n | pos | variant | AUROC (oof) |"
        " fold mean ± sd | AP | null | p |",
        "|---|---|---|---:|---:|---|---:|---|---:|---:|---:|",
    ]
    for cell in results:
        if cell is None or cell.get("status") != "ok":
            continue
        if cell.get("kind", "classification") != "classification":
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
    # 4 = the header lines alone; nothing of this kind was fit.
    return lines if len(lines) > 4 else []


def write_results(results: list[dict], out_dir: Path) -> None:
    """Write the combined JSON plus one ``<model>/embedding_results.json``.

    Per-model files are what spec 5.1 asks for (the probes are fit per
    model); the combined file at the root keeps the pooled fit and the
    skipped-cell record in one place. ``probe_results.json`` is written
    alongside under its historical name so anything already reading it
    keeps working.
    """
    import json

    out_dir.mkdir(parents=True, exist_ok=True)
    payload = [r for r in results if r]
    blob = json.dumps(payload, indent=2, default=str)
    (out_dir / "embedding_results.json").write_text(blob)
    (out_dir / "probe_results.json").write_text(blob)
    for model in sorted({r.get("model") for r in payload} - {None, "POOLED"}):
        model_dir = out_dir / str(model)
        model_dir.mkdir(parents=True, exist_ok=True)
        (model_dir / "embedding_results.json").write_text(
            json.dumps(
                [r for r in payload if r.get("model") == model],
                indent=2,
                default=str,
            )
        )
    (out_dir / "probe_report.md").write_text(render_report(results))


def render_report(results: list[dict]) -> str:
    lines = list(_PREAMBLE)
    regression = _regression_rows(results)
    classification = _classification_rows(results)
    if regression:
        lines += regression + [""]
    if classification:
        lines += classification + [""]
    skipped = [c for c in results if c and c.get("status") == "skipped"]
    if skipped:
        lines += ["## Skipped cells", ""]
        lines += [
            f"- {c['label']} / {c['channel']} / {c['model']}: "
            f"{c['reason']} (n={c['n']})"
            for c in skipped
        ]
    return "\n".join(lines) + "\n"
