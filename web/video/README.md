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

## 시네마틱 인서트 자리 (Higgsfield 등으로 나중에 만들 것)

| 파일 | 들어가는 곳 |
|---|---|
| `public/inserts/opening.mp4` | 첫 장면(제목). 네 에이전트의 오프닝 샷. 제목과 자막이 위에 얹힌다 |
| `public/inserts/exit.mp4` | ② 풀이 전 대화의 EXIT 줄("solver가 아니면 EXIT로 떠날 수 있습니다…"). 보라가 문으로 나가는 순간 |

파일이 있으면 그 자리에서 애니메이션 대신 그 영상을 소리 없이(`OffthreadVideo`, muted) 화면 가득 틀고, 내레이션과 자막은
그대로 둔다. 영상이 그 줄보다 길면 줄이 영상 길이만큼 늘어나고, 짧으면 마지막 프레임에서 멈춘다. 없으면 애니메이션 판이 나온다.
16:9(1920×1080 권장) H.264 mp4로 넣고 `npm run build`(또는 `npm run scan` 뒤 `npm start`로 미리 보기). 인서트의 화면은
EXIT 직후의 상태(보라가 떠나고 빈자리)와 이어져야 한다.

## 파일

- `src/timeline.mjs` 시계(줄 · 장면 길이, 장 목록) — 컴포지션과 `scripts/build.mjs`가 같이 쓴다
- `src/ArenaRules.tsx` 장면 순서 · 전환 · 음성 배치, `src/scenes/*.tsx` 장면, `src/ui.tsx` 공용 부품, `src/theme.ts` 색 · 글자 크기 · 움직임
- `src/generated/media.json` 음성 · 인서트 길이(`scripts/scan.mjs`가 씀)
- `public/sprites/` 논문 그림의 트레이닝복 스프라이트(`paper/cogsci2027/ko/figures/tracksuit_20261105/sprites/`를 높이 760으로 줄임),
  `public/fig1.png` 논문 Figure 1(한 라운드), `public/narration/` 음성
