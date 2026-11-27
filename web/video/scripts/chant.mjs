// The trailer's opening sound: the line of the children's game, "무궁화 꽃이 피었습니다", read slowly by a high
// synthetic voice (edge-tts) and made uneasy with ffmpeg: a copy an octave down under it, a long echo, the top end
// taken off -> public/sfx/chant.mp3. The words are the traditional game's; no recording from anywhere is used.
//   node scripts/chant.mjs      (part of npm run tts:trailer)
import { execFileSync } from "node:child_process";
import { mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const OUT = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "sfx");
const raw = join(tmpdir(), `arena-chant-${process.pid}.mp3`);
mkdirSync(OUT, { recursive: true });
for (let tries = 1; ; tries++) {  // the free endpoint now and then sends no audio: wait and ask again
  try {
    execFileSync("uvx", ["edge-tts", "--voice", "ko-KR-SunHiNeural", "--rate=-38%", "--pitch=+45Hz", "--text", "무궁화, 꽃이, 피었습니다.",
      "--write-media", raw], { stdio: ["ignore", "ignore", "pipe"] });
    break;
  } catch (e) {
    if (tries >= 5) { process.stderr.write(String(e.stderr || e)); throw e; }
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 3000 * tries);
  }
}
const graph = [
  "[0:a]aresample=24000,silenceremove=start_periods=1:start_silence=0.05:start_threshold=-42dB,asplit=2[a][b]",
  "[a]highpass=f=180,lowpass=f=3600[hi]",
  "[b]asetrate=12000,aresample=24000,atempo=2.0,lowpass=f=900,volume=0.5[lo]",   // the same words an octave down
  "[hi][lo]amix=inputs=2:normalize=0,aecho=0.8:0.8:160|340|560:0.42|0.3|0.2,apad=pad_dur=1.2,loudnorm=I=-19:TP=-2:LRA=11[out]",
].join(";");
execFileSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", "-i", raw, "-filter_complex", graph, "-map", "[out]", "-ar", "44100", "-ac", "1",
  "-c:a", "libmp3lame", "-b:a", "96k", join(OUT, "chant.mp3")], { stdio: "inherit" });
rmSync(raw, { force: true });
console.log("sfx chant.mp3");
