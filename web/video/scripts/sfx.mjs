// The drama version's sound bed and effects, synthesised with ffmpeg (sine sums, decays and seeded noise; no samples,
// no music from anywhere): public/sfx/<name>.mp3. Deterministic, so a rerun gives the same files.
//   drone  24 s loop: two low tones a fifth apart, a slow swell, a little filtered noise (the whole video, quiet)
//   tick   2 s loop: a clock's tick and tock          pulse  1 s loop: a low double beat (the EXIT walk, the shutdown)
//   clunk  a spotlight switching on                   hit    a low boom (title cards, the door, a wrong answer)
//   whoosh the EXIT door opening (air)                thud   the door closing
//   power  a falling tone (an agent shutting down)     chime  tokens moving (GIVE, a refund)
//   step   one footfall (the trailer's walk to the door)
//   horn   a grand entrance: two notes of low brass, the second a fourth lower and longer (the trailer: the rules begin)
//   bell1-3 three music-box notes going down (the trailer's opening, one for each shape of the mask)
// The opening's chant is a voice, not a synthesised effect: scripts/chant.mjs.
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
  step: [0.3, `${att(900)}*(0.9*sin(2*PI*74*t)*exp(-t*34)+0.35*${noise}*exp(-t*90))`, "lowpass=f=900"],
  horn: [5.5, (() => {
    // two notes of low brass, each struck with a sub-bass thump: D (0 s), then A a fourth below, longer (1.05 s)
    const u = (t0) => `max(0,t-${t0})`;
    const tone = (f, t0) => [1, 2, 3, 4, 5].map((k) => `${(0.12 / k).toFixed(3)}*sin(2*PI*${k * f}*${u(t0)})`).join("+");
    const note = (fs, t0, dec) => `gte(t,${t0})*(1-exp(-${u(t0)}*22))*exp(-${u(t0)}*${dec})*(${fs.map((f) => tone(f, t0)).join("+")})`;
    const thump = (t0, v) => `${v}*gte(t,${t0})*sin(2*PI*(38*${u(t0)}+52*(1-exp(-8*${u(t0)}))/8))*exp(-${u(t0)}*3.2)`;
    return `${thump(0, 0.5)}+${thump(1.05, 0.65)}+${note([73.42, 110, 146.83], 0, 2.1)}+${note([55, 82.41, 110, 164.81], 1.05, 0.75)}`;
  })(), "lowpass=f=2400,aecho=0.8:0.75:70|150|290:0.3|0.2|0.12"],
  bell1: [2.2, `${att(1500)}*(0.5*sin(2*PI*659.3*t)+0.2*sin(2*PI*1322*t)+0.08*sin(2*PI*1985*t))*exp(-t*2.6)`, "aecho=0.8:0.7:120|260:0.3|0.18"],
  bell2: [2.2, `${att(1500)}*(0.5*sin(2*PI*523.3*t)+0.2*sin(2*PI*1049*t)+0.08*sin(2*PI*1576*t))*exp(-t*2.6)`, "aecho=0.8:0.7:120|260:0.3|0.18"],
  bell3: [2.6, `${att(1500)}*(0.5*sin(2*PI*440*t)+0.2*sin(2*PI*883*t)+0.08*sin(2*PI*1326*t))*exp(-t*2.2)`, "aecho=0.8:0.7:120|260:0.3|0.18"],
  chime: [1.6, `${att(800)}*(0.45*sin(2*PI*880*t)*exp(-t*3)+0.3*sin(2*PI*1318.5*t)*exp(-t*4))`, "anull"],
};

mkdirSync(OUT, { recursive: true });
const only = process.argv.slice(2);  // names to make (default: all)
for (const [name, [dur, expr, post]] of Object.entries(SOUNDS)) {
  if (only.length && !only.includes(name)) continue;
  execFileSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
    `aevalsrc='${expr}':s=${SR}:d=${dur}`, "-af", `${post},alimiter=limit=0.7`, "-ac", "1", "-c:a", "libmp3lame", "-b:a", "96k",
    join(OUT, `${name}.mp3`)], { stdio: "inherit" });
  console.log(`sfx ${name}.mp3 (${dur} s)`);
}
