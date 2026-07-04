// Pure builder for the human-vs-LLM rank ladder shown on the campaign report.
// UMD: usable via `require` in node tests and as window.squidArenaHelpers in the browser.
(function (factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window !== "undefined") {
    window.squidArenaHelpers = window.squidArenaHelpers || {};
    window.squidArenaHelpers.buildRankLadder = api.buildRankLadder;
  }
})(function () {
  // models: [{ model_label, avg_score_per_game }]; you: { label, score }
  function buildRankLadder(models, you) {
    if (!models || models.length === 0) return null;

    const entries = models.map((m) => ({
      label: m.model_label,
      score: m.avg_score_per_game,
      isYou: false,
    }));
    entries.push({ label: you.label, score: you.score, isYou: true });

    // score desc; within a tie, non-You before You; then label asc.
    entries.sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      if (a.isYou !== b.isYou) return a.isYou ? 1 : -1;
      return a.label.localeCompare(b.label);
    });
    entries.forEach((e, i) => (e.rank = i + 1));

    const N = entries.length;
    const r = entries.find((e) => e.isYou).rank;

    // Window = {1} ∪ {r-1, r, r+1} (clamped to [1, N]).
    const show = new Set([1, r]);
    if (r - 1 >= 1) show.add(r - 1);
    if (r + 1 <= N) show.add(r + 1);

    const items = [];
    let prev = 0;
    for (const rank of Array.from(show).sort((a, b) => a - b)) {
      if (rank - prev > 1) items.push({ type: "gap" });
      const e = entries[rank - 1];
      items.push({
        type: "row",
        rank: e.rank,
        label: e.label,
        score: e.score,
        isYou: e.isYou,
        isLeader: e.rank === 1,
      });
      prev = rank;
    }

    const above = r > 1 ? entries[r - 2].label : null;
    const below = r < N ? entries[r].label : null;
    let headline;
    if (r === 1) headline = `#1 of ${N} — you beat every LLM.`;
    else if (r === N) headline = `#${r} of ${N} — below ${above}, dead last.`;
    else headline = `#${r} of ${N} — below ${above}, above ${below}.`;

    return { rank: r, total: N, headline, items };
  }

  return { buildRankLadder };
});
