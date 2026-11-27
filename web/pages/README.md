# web/pages/

사이트의 페이지는 모두 여기에 폴더 하나씩 있다. **폴더를 지우면 그 페이지와 그 API만 사라진다.** 여러 페이지가 함께
쓰는 것만 `web/server/`(앱 · 저장소 · 게임 정의 · 런 폴더)와 `web/shared/`(공용 CSS · JS · 이미지)에 둔다.

| 폴더 | 페이지 | 주소 | 비고 |
|---|---|---|---|
| `home/` | 랜딩 | `/`, `/index.html`, `/about.html`(옛 주소) | |
| `arena/` | 멀티플레이 아레나 | `/arena.html`, `/api/models`, `/api/rooms...` | 방 엔진 `engine.py` |
| `minigames/` | 미니 게임 소개 | `/minigames.html` | 카드 다섯 장(그림 + 이름), 누르면 설명. 플레이와 API는 없음. 숫자는 `squid/configs`의 각 설정을 따름 |
| `leaderboard/` | 리더보드 | `/leaderboard.html`, `/api/leaderboard*` | 사람 탭은 아레나 방의 run dir을 읽는다 |
| `monitor/` | 게임 기록 | `/monitor/...` | 화면 파일은 `tools/monitor`의 것(`static/` 없음) |
| `probe/` | 5.1 생존 동기 설문 | `/probe.html`, `/api/probe` | 짝 실험 `experiments/refill/`. 11-26부터 쓰지 않음: 모든 페이지에서 링크를 뺌(주소로만 열림) |

## 한 페이지 폴더의 모양

```
web/pages/<page>/
├─ __init__.py   # mount(app, site): 이 페이지의 API 경로를 붙이고 serve_static(app, static/)
├─ static/       # 사이트 루트에 그대로 놓이는 파일 (공용 파일은 web/shared 것을 상대 경로로 읽음)
├─ *.py          # 이 페이지만 쓰는 서버 코드 (예: arena/engine.py, leaderboard/humans.py)
└─ test_*.py     # 이 페이지의 테스트 (CI: pytest web/tests web/pages)
```

## 붙는 방식

- **API 서버**: `web/server/app.py`가 이 폴더의 하위 폴더마다 `mount(app, site)`를 부른다. 이름을 적지 않는다.
- **GitHub Pages**: 배포 워크플로가 `web/shared`에 `web/pages/*/static`을 겹쳐 사이트를 만든다. 배포 이미지는 `web/pages`를 통째로 복사한다.
- **다른 페이지의 링크**: 사이트 안의 `.html` 링크는 대상 페이지가 없으면 숨는다(`web/shared/site-lang.js`가 HEAD로 확인).
- **DB**: 페이지가 자기 표를 처음 쓸 때 만든다(`CREATE TABLE IF NOT EXISTS`). 폴더를 지워도 배포 DB의 표는 남는다.
- **예외 하나**: 리더보드의 사람 탭과 게임 기록의 방 연결은 아레나 방을 전제로 한다. 아레나 폴더를 지우면 두 페이지는
  그대로 뜨지만, 방을 플레이해 데이터를 만드는 테스트 4개는 건너뛴다(`web/testing.py`의 `needs_arena`).

## 지울 때 확인한 것 (11-24)

페이지 폴더를 하나씩 지운 복사본에서 앱이 뜨고, 남은 페이지가 모두 200으로 열리고, 남은 웹 테스트가 통과했다
(아레나를 지운 경우 12 통과 · 4 건너뜀).
