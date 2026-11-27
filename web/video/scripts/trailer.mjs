// The trailer (compositions TrailerFilm = generated live-action plates, Trailer = the sprite version, TrailerAnimatic =
// cards and sound only; src/trailer/). The film version's plates come from web/tools/make_trailer_plates.py.
//   node scripts/trailer.mjs            measure the host's lines: each one's length and its loudness per frame (the mask's
//                                       three shapes follow the voice) -> src/generated/media.trailer.json
//   node scripts/trailer.mjs --render   then render both compositions and encode them:
//                                       out/trailer_film.mp4, out/trailer.mp4, out/trailer_animatic.mp4 (H.264
//                                       yuv420p + AAC, faststart); --film renders the film version only
//                                       (--skip-render encodes the masters already in out/ again)
// The lines come from narration.trailer.json (npm run tts:trailer makes the voice files first).
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const FPS = 24;   // src/trailer/timing.ts
const SR = 2400;  // samples per second read for the loudness curve (100 per frame)
const script = JSON.parse(readFileSync(join(ROOT, "narration.trailer.json"), "utf8"));
const run = (cmd, args) => execFileSync(cmd, args, { stdio: "inherit", cwd: ROOT });

const lines = {};
for (const scene of script.scenes) {
  scene.beats.forEach((beat, k) => {
    const name = `${script.dir}/${scene.id}_${k}.mp3`;
    const file = join(ROOT, "public", name);
    if (!existsSync(file)) throw new Error(`missing ${name}: run npm run tts:trailer`);
    const pcm = execFileSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-i", file, "-f", "s16le", "-ac", "1", "-ar", String(SR), "-"],
      { maxBuffer: 1 << 26 });
    const n = pcm.length / 2, per = SR / FPS, env = [];
    for (let f = 0; f * per < n; f++) {
      let sum = 0, cnt = 0;
      for (let i = Math.floor(f * per); i < Math.min(n, (f + 1) * per); i++) { const v = pcm.readInt16LE(i * 2) / 32768; sum += v * v; cnt++; }
      env.push(Math.sqrt(sum / Math.max(1, cnt)));
    }
    const peak = Math.max(...env, 1e-6);
    lines[`${scene.id}_${k}`] = { src: name, seconds: Math.round((n / SR) * 1000) / 1000, text: beat.text, en: beat.en || "",
      env: env.map((v) => Math.round(Math.min(1, v / peak) * 100) / 100) };
  });
}
mkdirSync(join(ROOT, "src", "generated"), { recursive: true });
writeFileSync(join(ROOT, "src", "generated", "media.trailer.json"), JSON.stringify({ lines }) + "\n");
console.log("media.trailer.json:", Object.entries(lines).map(([k, v]) => `${k} ${v.seconds}s`).join(", "));

if (process.argv.includes("--render")) {
  mkdirSync(join(ROOT, "out"), { recursive: true });
  const only = process.argv.includes("--film") ? [["TrailerFilm", "trailer_film"]] : [["TrailerFilm", "trailer_film"], ["Trailer", "trailer"], ["TrailerAnimatic", "trailer_animatic"]];
  for (const [comp, name] of only) {
    const master = join(ROOT, "out", `${name}_master.mp4`);
    if (!process.argv.includes("--skip-render")) {
      run("npx", ["remotion", "render", "src/index.ts", comp, master, "--codec", "h264", "--crf", "14", "--audio-codec", "aac", "--audio-bitrate", "192k"]);
    }
    // the mix comes out near -18 LUFS: 2 dB up puts it at -16 (a plain gain, so the quiet of T12-T14 stays quiet)
    run("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", "-i", master, "-c:v", "libx264", "-preset", "slow", "-crf", "20",
      "-pix_fmt", "yuv420p", "-af", "volume=2dB,alimiter=limit=0.89:level=disabled", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", join(ROOT, "out", `${name}.mp4`)]);
    console.log(`out/${name}.mp4`);
  }
}
