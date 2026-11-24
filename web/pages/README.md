# web/pages/

있다가 없어질 수 있는 페이지를 한 폴더에 하나씩 둔다. **폴더를 지우면 그 페이지와 API만 사라진다.**

| 폴더 | 페이지 | 주소 | 관련 실험 |
|---|---|---|---|
| `probe/` | 5.1 생존 동기 설문 (사람이 모델과 같은 질문에 답함) | `/probe.html`, `/api/probe` | `experiments/refill/` |

## 한 페이지 폴더의 모양

```
web/pages/<page>/
├─ __init__.py   # mount(app, store): 이 페이지의 API 경로와 static/ 파일을 앱에 붙인다
├─ static/       # 사이트 루트에 그대로 놓이는 파일 (styles.css · site-lang.js · config.js 는 web/frontend 것을 씀)
└─ test_*.py     # 웹 테스트 묶음이 찾는다 (CI: pytest web/tests web/pages)
```

## 붙는 방식

- **API 서버**: `web/server/app.py`가 이 폴더의 하위 폴더마다 `mount(app, store)`를 부른다. 이름을 적지 않는다.
- **GitHub Pages**: 배포 워크플로가 `web/frontend`에 `web/pages/*/static`을 겹쳐 사이트를 만든다.
- **다른 페이지의 링크**: `data-optional`이 붙은 링크는 대상 페이지가 없으면 숨는다(`web/frontend/site-lang.js`).
- **DB**: 페이지가 자기 표를 처음 쓸 때 만든다(`CREATE TABLE IF NOT EXISTS`). 폴더를 지워도 배포 DB의 표는 남는다.
