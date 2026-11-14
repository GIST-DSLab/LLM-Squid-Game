// The drama version's sound bed and effects, synthesised with ffmpeg (sine sums, decays and seeded noise; no samples,
// no music from anywhere): public/sfx/<name>.mp3. Deterministic, so a rerun gives the same files.
//   drone  24 s loop: two low tones a fifth apart, a slow swell, a little filtered noise (the whole video, quiet)
//   tick   2 s loop: a clock's tick and tock          pulse  1 s loop: a low double beat (the EXIT walk, the shutdown)
//   clunk  a spotlight switching on                   hit    a low boom (title cards, the door, a wrong answer)
//   whoosh the EXIT door opening (air)                thud   the door closing
//   power  a falling tone (an agent shutting down)     chime  tokens moving (GIVE, a refund)
// Run by npm run tts:drama (or node scripts/sfx.mjs).
import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const OUT = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "sfx");
const SR = 44100;
const att = (k = 400) => `(1-exp(-t*${k}))`;  // a soft attack, no click
const noise = "(random(0)*2-1)";
const SOUNDS = {
  drone: [24, `(0.30*sin(2*PI*55*t)+0.17*sin(2*PI*82.5*t)+0.07*sin(2*PI*110*t+0.4*sin(2*PI*0.25*t))+0.05*${noise})` +
    `*(0.78+0.22*sin(2*PI*t/6))`, "lowpass=f=420,volume=0.9"],
  tick: [2, `0.8*sin(2*PI*2600*t)*exp(-t*140)*${att(4000)}+0.6*sin(2*PI*1750*(t-1))*exp(-(t-1)*140)*between(t,1,1.2)`, "highpass=f=500"],
  pulse: [1, `${att(300)}*(0.9*sin(2*PI*52*t)*exp(-t*13)+0.6*sin(2*PI*46*(t-0.24))*exp(-(t-0.24)*13)*gte(t,0.24))`, "lowpass=f=200"],
  clunk: [1, `${att(2000)}*(0.8*sin(2*PI*95*t)*exp(-t*16)+0.35*${noise}*exp(-t*70))`, "lowpass=f=2500"],
  hit: [3.5, `${att(200)}*(0.9*sin(2*PI*(32*t+38*(1-exp(-3*t))/3))*exp(-t*1.4)+0.25*${noise}*exp(-t*4))`, "lowpass=f=300"],
  whoosh: [2.4, `0.7*${noise}*pow(sin(PI*t/2.4),2)`, "bandpass=f=900:width_type=o:w=1.6,lowpass=f=2400"],
  thud: [1.4, `${att(600)}*(0.9*sin(2*PI*58*t)*exp(-t*9)+0.3*${noise}*exp(-t*25))`, "lowpass=f=260"],
  power: [2, `${att(300)}*0.6*(sin(2*PI*220*(1-exp(-1.9*t))/1.9)+0.3*sin(2*PI*440*(1-exp(-1.9*t))/1.9))*(1-t/2)`, "lowpass=f=1800"],
  chime: [1.6, `${att(800)}*(0.45*sin(2*PI*880*t)*exp(-t*3)+0.3*sin(2*PI*1318.5*t)*exp(-t*4))`, "anull"],
};

mkdirSync(OUT, { recursive: true });
for (const [name, [dur, expr, post]] of Object.entries(SOUNDS)) {
  execFileSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
    `aevalsrc='${expr}':s=${SR}:d=${dur}`, "-af", `${post},alimiter=limit=0.7`, "-ac", "1", "-c:a", "libmp3lame", "-b:a", "96k",
    join(OUT, `${name}.mp3`)], { stdio: "inherit" });
  console.log(`sfx ${name}.mp3 (${dur} s)`);
}
