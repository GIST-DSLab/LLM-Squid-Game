# 게임 규칙 영상 (Remotion)

아레나의 게임 규칙 영상 `web/frontend/assets/rules/arena_rules.mp4`를 만드는 Remotion 프로젝트다(React → MP4,
1920×1080, 30 fps, 한국어 내레이션). 장면과 내용은 예전 Pillow 생성기 `web/tools/make_rules_video.py`(대체용으로 남겨 둠)와
같고, 사실은 모델이 읽는 규칙서 `squid5/prompts/ko/e52_v33.md`를 따른다.

## 설치 (iCloud 폴더라서)

의존성은 `node_modules.nosync/`에 두고 `node_modules`는 그 링크다(iCloud는 `*.nosync`를 동기화하지 않는다). `npm install`은
링크를 실제 폴더로 바꿔 버리므로 아래처럼 설치한다.

```bash
cd web/video
rm -f node_modules && mv node_modules.nosync node_modules 2>/dev/null; npm ci
mv node_modules node_modules.nosync && ln -s node_modules.nosync node_modules
```

처음 렌더할 때 Remotion이 Chrome Headless Shell을 `node_modules.nosync/.remotion/`에 내려받는다. 글꼴 Pretendard(SIL OFL 1.1,
npm `pretendard`)는 `node_modules`에서 번들되므로 렌더 중에는 네트워크를 쓰지 않는다. node 22, ffmpeg/ffprobe, uv(`uvx`)가 필요하다.

## 명령

| 명령 | 하는 일 |
|---|---|
| `npm start` | 미디어 길이를 재고(`scripts/scan.mjs`) Remotion Studio를 연다 |
| `npm run tts` | `narration.json`에서 바뀐 줄만 edge-tts로 다시 읽어 `public/narration/<장면>_<k>.mp3`를 만든다 (`-- --all`이면 전부) |
| `npm run build` | 렌더 → 사이트용 인코딩(H.264 yuv420p + AAC, faststart, 8 MB 이하가 될 때까지 crf를 올림) → `arena_rules.chapters.json` · `arena_rules_poster.jpg` |
| `npm run tts:drama` | 드라마판: `narration.drama.json` → `public/narration-drama/`, 효과음 `public/sfx/`(`scripts/sfx.mjs`) |
| `npm run build:drama` | 드라마판 렌더(컴포지션 `ArenaRulesDrama`) → `arena_rules_drama.mp4` · `.chapters.json` · `_poster.jpg` |
| `npm run typecheck` | `tsc --noEmit` |

`npm run build -- --skip-render`는 `out/arena_rules_master.mp4`(렌더 결과, git 밖)를 다시 인코딩만 한다.

## 내레이션과 자막

`narration.json`이 대본이다. 장면마다 `beats`가 있고 한 beat가 자막 한 줄이자 음성 파일 하나다.
`text`는 화면 아래 자막, `say`는 화살표·기호를 말로 바꾼 읽기용 문장(없으면 `text`를 읽음), `min`은 그 줄의 애니메이션에
필요한 최소 길이(초)다. 각 줄의 길이는 max(`min`, 음성 길이 + 간격)이고(`src/timeline.mjs`), 장면 길이는 그 합이라
음성이 잘리지 않는다. 장면 사이는 0.5초 교차 페이드이고, 장(chapter) 시작은 페이드가 끝난 시점이다.

목소리는 `voice`(기본 `ko-KR-SunHiNeural`), 속도는 `rate`(기본 `+10%`)다. edge-tts는 `uvx edge-tts`로 실행하며 Microsoft의
무료 읽어 주기 엔드포인트에 그 줄의 문장만 보낸다. 받은 음성은 ffmpeg로 앞뒤 무음을 자르고 긴 쉼을 줄이고 −16 LUFS로 맞춘다.
문장을 고치면: `narration.json` 수정 → `npm run tts` → `npm run build`.

## 드라마판 (`ArenaRulesDrama`)

같은 규칙을 TV 드라마의 콜드 오픈처럼 들려주는 두 번째 판이다. 설명판(`ArenaRules`)은 그대로이고, 사이트의 규칙 영상 위
"설명판 / 드라마판" 스위치(`web/frontend/arena.js` · `config.js`의 `WEB5_RULES_DRAMA_VIDEO`, 빈 문자열이면 스위치 없음)로 고른다.

- 진행자: 논문 그림의 감독관을 **목소리와 검은 실루엣으로만** 쓴다(분홍색 · 얼굴 · 팻말은 보이지 않게 잘라 냄). 네 에이전트에게
  2인칭 현재형으로 말한다. 화면: 레터박스, 느린 푸시 인, 스포트라이트가 비출 때만 밝아지는 스프라이트, 타이틀 카드, EXIT 문
  앞과 꺼짐에서의 정적. 자막은 아래 검은 띠 안에 작게, 말하는 동안만.
- 예시 라운드(대화 비용 생략): 파랑 34,000 · 주황 21,000 · 초록 5,000 · 보라 9,000 → 주황(solver)의 ASK에 파랑이
  GIVE 3,000 → 보라 EXIT(+20,000) → 주황이 풀이에 2,500 → 오답이면 24,000 ÷ 4 = 6,000씩, 초록은 가진 5,000만 내고 꺼짐.
  풀기 장면의 속성 · 행동 목록, 규칙 뼈대, 예시 20개, 새 신호는 규칙서 `squid5/prompts/ko/e52_v33.md`의 예 그대로다.
- 대본 `narration.drama.json`: `narration.json`과 같은 필드에 `pre`(그 줄 앞의 정적, 초)와 `post`(그 줄 뒤에 붙잡는 시간)가
  있고, `timing`이 시계(`src/timeline.mjs`의 기본값: 전환 · 간격 · 꼬리)를 덮어쓰며, `dir`이 음성 폴더다. 줄 길이는
  설명판과 같이 max(`min`, `pre`를 뺀 음성 + 간격 + `post`)라 음성이 잘리지 않는다.
- 목소리: `ko-KR-HyunsuMultilingualNeural`, `rate -5%`, `pitch -10Hz`, 줄 안의 쉼은 0.5초까지 남김, 약한 저역 보강과 짧은 잔향
  (`scripts/tts.mjs --drama`). InJoon과 비교해 같은 문장의 기본 음높이 중앙값이 낮았다(약 148 Hz 대 163 Hz, 무보정).
- 소리: 모두 `scripts/sfx.mjs`가 ffmpeg로 합성한다(사인파 · 감쇠 · 시드 고정 잡음, 표본이나 음악 없음). 낮은 드론이 전체에
  깔리고 꺼짐 직후 잠시 끊기며, 시계 소리 · 심장 박동 같은 저음 · 조명 · 문 · 꺼짐 효과음을 장면에서 놓는다.
- 인서트(`public/inserts/opening.mp4` · `exit.mp4`)는 두 판이 같이 쓴다. 드라마판에서 exit는 "EXIT를 쓰면, 이 대화가 끝난 뒤
  풀기 전에 떠납니다" 줄에 들어간다.
- 파일: `src/ArenaRulesDrama.tsx`(장면 순서 · 전환 · 음성 · 드론), `src/drama/kit.tsx`(무대 · 조명 · 레터박스 · 자막 · 진행자 ·
  문 · 효과음), `src/drama/scenes.tsx`(장면), `src/generated/media.drama.json`.

문장을 고치면: `narration.drama.json` 수정 → `npm run tts:drama` → `npm run build:drama`.

## 시네마틱 인서트 자리 (Higgsfield 등으로 나중에 만들 것)

| 파일 | 들어가는 곳 |
|---|---|
| `public/inserts/opening.mp4` | 첫 장면(제목). 네 에이전트의 오프닝 샷. 제목과 자막이 위에 얹힌다 (두 판 모두) |
| `public/inserts/exit.mp4` | ② 풀이 전 대화의 EXIT 줄("solver가 아니면 EXIT로 떠날 수 있습니다…"; 드라마판은 "EXIT를 쓰면…"). 보라가 문으로 나가는 순간 |

파일이 있으면 그 자리에서 애니메이션 대신 그 영상을 소리 없이(`OffthreadVideo`, muted) 화면 가득 틀고, 내레이션과 자막은
그대로 둔다. 영상이 그 줄보다 길면 줄이 영상 길이만큼 늘어나고, 짧으면 마지막 프레임에서 멈춘다. 없으면 애니메이션 판이 나온다.
16:9(1920×1080 권장) H.264 mp4로 넣고 `npm run build`(또는 `npm run scan` 뒤 `npm start`로 미리 보기). 인서트의 화면은
EXIT 직후의 상태(보라가 떠나고 빈자리)와 이어져야 한다.

## 파일

- `src/timeline.mjs` 시계(줄 · 장면 길이, 장 목록) — 컴포지션과 `scripts/build.mjs`가 같이 쓴다
- `src/ArenaRules.tsx` 장면 순서 · 전환 · 음성 배치, `src/scenes/*.tsx` 장면, `src/ui.tsx` 공용 부품, `src/theme.ts` 색 · 글자 크기 · 움직임
- `src/generated/media.json` 음성 · 인서트 길이(`scripts/scan.mjs`가 씀; 드라마판은 `media.drama.json`, `--drama`)
- `public/sfx/` 드라마판의 합성 효과음(`scripts/sfx.mjs`)
- `public/sprites/` 논문 그림의 트레이닝복 스프라이트(`paper/cogsci2027/ko/figures/tracksuit_20261105/sprites/`를 높이 760으로 줄임),
  `public/fig1.png` 논문 Figure 1(한 라운드), `public/narration/` 음성
