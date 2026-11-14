// Narration: one mp3 per caption beat (public/narration/<scene>_<k>.mp3) from narration.json, with edge-tts
// (Microsoft's free read-aloud voices; only the beat's text is sent). Run through uvx, so nothing is installed here.
// Each take is then cut tight with ffmpeg (leading / trailing silence off, long pauses shortened) and levelled to
// -16 LUFS, so beats can sit close together and the voice is clear over the site's speakers.
// A beat is regenerated only when its text, voice or rate changed (public/narration/manifest.json keeps the hashes).
//   npm run tts            # changed beats only
//   npm run tts -- --all   # every beat
// --drama reads narration.drama.json instead (the drama version, npm run tts:drama): its voice, rate and pitch, its
// folder (public/narration-drama/), pauses inside a line kept up to 0.5 s and a little low end and room on the voice.
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const DRAMA = process.argv.includes("--drama");
const script = JSON.parse(readFileSync(join(ROOT, DRAMA ? "narration.drama.json" : "narration.json"), "utf8"));
const OUT = join(ROOT, "public", script.dir || "narration");
const all = process.argv.includes("--all");
const TRIM = DRAMA
  ? ["silenceremove=start_periods=1:start_silence=0.05:start_threshold=-42dB:stop_periods=-1:stop_duration=0.5:stop_silence=0.5:stop_threshold=-42dB",
    "areverse", "silenceremove=start_periods=1:start_silence=0.08:start_threshold=-42dB", "areverse",
    "apad=pad_dur=0.15", "bass=g=3:f=110", "aecho=0.85:0.6:45|80:0.10|0.06", "loudnorm=I=-16:TP=-1.5:LRA=11"].join(",")
  : ["silenceremove=start_periods=1:start_silence=0.05:start_threshold=-42dB:stop_periods=-1:stop_duration=0.3:stop_silence=0.3:stop_threshold=-42dB",
    "areverse", "silenceremove=start_periods=1:start_silence=0.08:start_threshold=-42dB", "areverse",
    "loudnorm=I=-16:TP=-1.5:LRA=11"].join(",");
const pitch = script.pitch ? [`--pitch=${script.pitch}`] : [];
const raw = join(tmpdir(), `arena-tts-${process.pid}.mp3`);
mkdirSync(OUT, { recursive: true });
const manPath = join(OUT, "manifest.json");
const man = existsSync(manPath) ? JSON.parse(readFileSync(manPath, "utf8")) : {};
const next = {};
let made = 0;
for (const scene of script.scenes) {
  scene.beats.forEach((beat, k) => {
    const name = `${scene.id}_${k}.mp3`;
    const say = beat.say ?? beat.text;
    const hash = createHash("sha1").update([script.voice, script.rate, say, TRIM, ...pitch].join("\n")).digest("hex").slice(0, 16);
    next[name] = hash;
    if (!all && man[name] === hash && existsSync(join(OUT, name))) return;
    for (let tries = 1; ; tries++) {  // the free endpoint now and then sends no audio: wait and ask again
      try {
        execFileSync("uvx", ["edge-tts", "--voice", script.voice, `--rate=${script.rate}`, ...pitch, "--text", say,
          "--write-media", raw], { stdio: ["ignore", "ignore", "pipe"] });
        break;
      } catch (e) {
        if (tries >= 5) { process.stderr.write(String(e.stderr || e)); throw e; }
        console.log(`tts ${name}: no audio (try ${tries}), retrying`);
        Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 3000 * tries);
      }
    }
    execFileSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", "-i", raw, "-af", TRIM, "-ar", "24000", "-ac", "1",
      "-c:a", "libmp3lame", "-b:a", "64k", join(OUT, name)], { stdio: "inherit" });
    rmSync(raw, { force: true });
    made++;
    console.log(`tts ${name}: ${say}`);
  });
}
for (const f of readdirSync(OUT)) if (f.endsWith(".mp3") && !(f in next)) rmSync(join(OUT, f));  // beats that were removed
writeFileSync(manPath, JSON.stringify(next, null, 1) + "\n");
console.log(`${made} beat(s) generated, ${Object.keys(next).length} in all`);
