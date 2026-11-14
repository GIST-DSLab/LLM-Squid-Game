// Measures what the composition needs to know before it renders: each narration beat's length and which
// cinematic inserts exist (public/inserts/opening.mp4, public/inserts/exit.mp4) with their lengths.
// Writes src/generated/media.json; run by npm start / tts / build.
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const script = JSON.parse(readFileSync(join(ROOT, "narration.json"), "utf8"));
const seconds = (file) => Number(execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration",
  "-of", "default=nw=1:nk=1", file], { encoding: "utf8" }).trim());

const audio = {};
for (const scene of script.scenes) {
  scene.beats.forEach((_, k) => {
    const name = `narration/${scene.id}_${k}.mp3`;
    const file = join(ROOT, "public", name);
    if (!existsSync(file)) throw new Error(`missing ${name}: run npm run tts`);
    audio[name] = Math.round(seconds(file) * 1000) / 1000;
  });
}
const inserts = {};
for (const id of ["opening", "exit"]) {
  const file = join(ROOT, "public", "inserts", `${id}.mp4`);
  inserts[id] = existsSync(file) ? { src: `inserts/${id}.mp4`, seconds: Math.round(seconds(file) * 1000) / 1000 } : null;
}
mkdirSync(join(ROOT, "src", "generated"), { recursive: true });
writeFileSync(join(ROOT, "src", "generated", "media.json"), JSON.stringify({ audio, inserts }, null, 1) + "\n");
console.log(`media.json: ${Object.keys(audio).length} beats, inserts ${JSON.stringify(inserts)}`);
