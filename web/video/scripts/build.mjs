// npm run build: measure the media, render the composition, encode the site's copy, write the chapters and the poster.
//   out/arena_rules_master.mp4                         Remotion's render (high quality, render scratch, not kept in git)
//   ../frontend/assets/rules/arena_rules.mp4          H.264 yuv420p + AAC, faststart, <= 8 MB (crf raised until it fits)
//   ../frontend/assets/rules/arena_rules.chapters.json the player's chapters (web/frontend/vplayer.js)
//   ../frontend/assets/rules/arena_rules_poster.jpg   a frame of the EXIT moment
// Options: --skip-render (re-encode the existing master), --max-mb 8
// --drama (npm run build:drama): the drama version instead — composition ArenaRulesDrama from narration.drama.json, to
//   out/arena_rules_drama_master.mp4 and arena_rules_drama.mp4 / .chapters.json / _poster.jpg (a frame at the EXIT door).
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { FPS, buildTimeline, chapters } from "../src/timeline.mjs";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const SITE = join(ROOT, "..", "frontend", "assets", "rules");
const DRAMA = process.argv.includes("--drama");
const NAME = DRAMA ? "arena_rules_drama" : "arena_rules";
const MASTER = join(ROOT, "out", `${NAME}_master.mp4`);
const OUT = join(SITE, `${NAME}.mp4`);
const arg = (name, dflt) => { const i = process.argv.indexOf(name); return i < 0 ? dflt : process.argv[i + 1]; };
const maxBytes = Number(arg("--max-mb", 8)) * 1e6;
const run = (cmd, args) => execFileSync(cmd, args, { stdio: "inherit", cwd: ROOT });

run("node", DRAMA ? ["scripts/scan.mjs", "--drama"] : ["scripts/scan.mjs"]);
const timeline = buildTimeline(JSON.parse(readFileSync(join(ROOT, DRAMA ? "narration.drama.json" : "narration.json"), "utf8")),
  JSON.parse(readFileSync(join(ROOT, "src", "generated", DRAMA ? "media.drama.json" : "media.json"), "utf8")));

mkdirSync(join(ROOT, "out"), { recursive: true });
if (!process.argv.includes("--skip-render")) {
  run("npx", ["remotion", "render", "src/index.ts", DRAMA ? "ArenaRulesDrama" : "ArenaRules", MASTER, "--codec", "h264", "--crf", "14",
    "--audio-codec", "aac", "--audio-bitrate", "192k"]);
}

let crf = 24;
for (;;) {
  run("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", "-i", MASTER, "-c:v", "libx264", "-preset", "slow", "-tune", "animation",
    "-crf", String(crf), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "64k", "-ac", "1", "-movflags", "+faststart", OUT]);
  const size = statSync(OUT).size;
  console.log(`crf ${crf}: ${(size / 1e6).toFixed(2)} MB`);
  if (size <= maxBytes || crf >= 34) break;
  crf += 2;
}

writeFileSync(join(SITE, `${NAME}.chapters.json`), JSON.stringify(chapters(timeline), null, 1) + "\n");
const poster = DRAMA ? timeline.scenes.find((s) => s.id === "exit") : timeline.scenes.find((s) => s.id === "talk");
const posterAt = DRAMA
  ? (poster.from + poster.beats[4].start + 1.8 * FPS) / FPS   // purple at the open EXIT door
  : (poster.from + poster.beats[2].start + 2.2 * FPS) / FPS;  // purple walking to the EXIT door
run("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", "-ss", posterAt.toFixed(3), "-i", OUT, "-frames:v", "1",
  "-vf", "scale=1280:-2", "-q:v", "3", join(SITE, `${NAME}_poster.jpg`)]);
console.log(`done: ${(timeline.total / FPS).toFixed(1)} s, chapters + poster written`);
