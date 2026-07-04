import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { buildRankLadder } = require("../../web/rank_ladder.js");

const MODELS = [
  { model_label: "Gemini", avg_score_per_game: 536 },
  { model_label: "Qwen", avg_score_per_game: 470 },
  { model_label: "GPT-OSS", avg_score_per_game: 351 },
  { model_label: "Nemotron", avg_score_per_game: 236 },
];

test("returns null when no models", () => {
  assert.equal(buildRankLadder([], { label: "You", score: 10 }), null);
});

test("You last: leader + gap + above + You, dead-last headline", () => {
  const r = buildRankLadder(MODELS, { label: "You", score: 10 });
  assert.equal(r.rank, 5);
  assert.equal(r.total, 5);
  assert.equal(r.headline, "#5 of 5 — below Nemotron, dead last.");
  assert.deepEqual(
    r.items.map((i) => (i.type === "gap" ? "gap" : `${i.rank}:${i.label}`)),
    ["1:Gemini", "gap", "4:Nemotron", "5:You"],
  );
  assert.equal(r.items.find((i) => i.isYou).label, "You");
  assert.equal(r.items[0].isLeader, true);
});

test("You middle: leader + gap + above + You + below", () => {
  const r = buildRankLadder(MODELS, { label: "You", score: 400 });
  assert.equal(r.rank, 3); // 536,470,400(You),351,236
  assert.equal(r.headline, "#3 of 5 — below Qwen, above GPT-OSS.");
  assert.deepEqual(
    r.items.map((i) => (i.type === "gap" ? "gap" : `${i.rank}:${i.label}`)),
    ["1:Gemini", "2:Qwen", "3:You", "4:GPT-OSS"],
  );
});

test("You first: leader row is You, beat-every headline, no gap", () => {
  const r = buildRankLadder(MODELS, { label: "You", score: 999 });
  assert.equal(r.rank, 1);
  assert.equal(r.headline, "#1 of 5 — you beat every LLM.");
  assert.deepEqual(
    r.items.map((i) => `${i.rank}:${i.label}`),
    ["1:You", "2:Gemini"],
  );
});

test("tie: You sorts last within its score group (never optimistic)", () => {
  const r = buildRankLadder(MODELS, { label: "You", score: 236 });
  assert.equal(r.rank, 5); // Nemotron 236 keeps rank 4, You rank 5
});
