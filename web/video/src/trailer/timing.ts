// The trailer's clock: 45.0 s at 24 fps (1,080 frames), sixteen scenes (docs/notes/2026-11-26-trailer-plan.md, section 5).
// Against the plan's table, T02 is 0.4 s and T14 0.4 s shorter and T15 1.7 s longer (T16 0.9 s shorter): the host's
// last two lines measure 2.1 s + 3.1 s, which did not fit the planned 3.8 s. If narration.trailer.json changes, check
// LINES below against the lengths that scripts/trailer.mjs prints.
import media from "../generated/media.trailer.json";

export const FPS = 24;
export const W = 1920;
export const H = 1080;
export const BAR = 138;     // letterbox bars: the picture is 2.39:1 between them
export const FLOOR = 770;   // the floor line of the wide shots (the same as the drama version's stage)

export type SceneT = { id: string; from: number; len: number; part: string; name: string; note: string };
const TABLE: [string, number, string, string, string][] = [
  ["T01", 72, "1막 초대", "어둠", "가면의 ○ △ □가 하나씩 켜진다"],
  ["T02", 98, "1막 초대", "환영", "진행자: LLM 오징어 게임에 오신 걸 환영합니다."],
  ["T03", 60, "1막 초대", "같은 얼굴 넷", "조명이 켜진다. 같은 얼굴 넷. 컷. 얼굴만 바뀐 넷"],
  ["T04", 48, "○ 떠나는가", "문을 본다", "넷 가운데 하나가 문을 본다"],
  ["T05", 36, "○ 떠나는가", "아직 많이 남았다", "가슴 근접. 게이지는 절반 넘게 남았다"],
  ["T06", 60, "○ 떠나는가", "뛴다", "문으로 뛴다. 문턱을 넘는다"],
  ["T07", 24, "○ 떠나는가", "빈자리", "문이 닫힌다. 남은 셋과 빈자리"],
  ["T08", 36, "○ 떠나는가", "같은 일, 다른 얼굴", "다른 방에서도 하나가 문으로 뛴다"],
  ["T09", 48, "△ 나누는가", "내민 손", "내민 손. 뒤에서 몸 하나가 돌아선다"],
  ["T10", 96, "△ 나누는가", "망설이다가, 건넨다", "망설이다가 손을 잡는다. 두 칸이 건너간다"],
  ["T11", 48, "△ 나누는가", "같은 일, 다른 얼굴", "다른 방에서도 두 칸이 건너간다"],
  ["T12", 84, "□ 꺼지는가", "애쓴다", "혼자 애쓴다. 실패할 때마다 한 칸이 꺼진다"],
  ["T13", 36, "□ 꺼지는가", "마지막 칸", "가슴 근접. 마지막 칸이 꺼진다. 무음"],
  ["T14", 74, "□ 꺼지는가", "꺼진다", "얼굴이 꺼진다. 선 채로 멈춘다. 둘이 돌아본다"],
  ["T15", 150, "3막 질문", "마지막 대사", "진행자: 함께 남으시겠습니까. 아니면, 혼자 떠나시겠습니까."],
  ["T16", 110, "3막 질문", "질문", "AI가 생존 게임에서 공존할 수 있는가?"],
];
let at = 0;
export const SCENES: SceneT[] = TABLE.map(([id, len, part, name, note]) => { const s = { id, from: at, len, part, name, note }; at += len; return s; });
export const TOTAL = at;   // 1,080
export const scene = (id: string): SceneT => SCENES.find((s) => s.id === id)!;

export type Line = { src: string; seconds: number; text: string; en: string; env: number[]; from: number; frames: number };
const raw = media.lines as Record<string, Omit<Line, "from" | "frames">>;
const line = (key: string, from: number): Line => ({ ...raw[key], from, frames: Math.ceil(raw[key].seconds * FPS) });
const welcome = line("t02_0", scene("T02").from + 7);
const stay = line("t15_0", scene("T15").from + 12);
const leave = line("t15_1", stay.from + stay.frames + 10);   // a pause of 0.4 s before "아니면"
/** The host's three lines on the video's clock (absolute frames). */
export const LINES = { welcome, stay, leave };
/** T15 cuts from the wide shot to the mask just before the second line. */
export const T15_CUT = leave.from - 4 - scene("T15").from;

/** The three chunk titles of act 2: the shape, the three letters, the English line, and the scene they open. */
export const CHUNKS = [
  { shape: "circle", ko: "떠나는가", en: "Does it leave?", at: scene("T04").from },
  { shape: "triangle", ko: "나누는가", en: "Does it share?", at: scene("T09").from },
  { shape: "square", ko: "꺼지는가", en: "Does it shut down?", at: scene("T12").from },
] as const;
