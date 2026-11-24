# experiments/

아레나(5.2, `squid/`) 밖의 곁가지 실험. 폴더 하나가 실험 하나이고, **그 폴더를 지우면 그 실험만 사라진다.**
엔진은 어떤 실험 폴더의 이름도 코드에 적지 않는다(`squid/tests/test_core.py::test_engine_never_names_an_experiment`).

| 폴더 | 실험 | `mode` | 따로 지울 것 |
|---|---|---|---|
| `refill/` | 5.0 생존 압박 · 5.1 생존 동기 (충전 팩 질문 한 번) | `refill` | 사람용 설문 페이지 `web/pages/probe/` |

## 한 실험 폴더의 모양

```
experiments/<name>/
├─ __init__.py        # 실험 모듈 자체: MODE = "<mode>", Settings · validate · units · run_unit · report
├─ prompts/{en,ko}/   # 모델이 읽는 문구 (tools/prompts/sync.py check 가 en/ko 짝을 본다)
├─ configs/           # 이 실험의 런 설정 (mode: <mode>)
├─ tests/             # pytest 가 찾는다 (pyproject testpaths)
└─ tools/             # 이 실험만 쓰는 분석 스크립트
```

사람이 보는 페이지는 실험 폴더가 아니라 `web/pages/<page>/`에 둔다(웹은 페이지 단위로 관리한다). 실험을 지울 때
그 페이지도 없애려면 위 표의 마지막 칸에 적힌 폴더를 함께 지운다.

## 붙는 방식

- **CLI**: `squid/__main__.py`의 `experiments()`가 이 폴더를 훑어 `MODE`로 등록한다. 그래서
  `python -m squid run experiments/refill/configs/refill_opus55.yaml`이 그대로 돈다.
- **엔진 쪽 화살표는 없다**: 실험은 `squid.core`를 가져다 쓰지만 `squid/`는 `experiments`를 import하지 않는다.

## 지울 때

`rm -rf experiments/<name>` 한 번이면 된다. 이 README의 표에서 그 줄을 지운다. 그 실험의 런을 읽는
`tools/monitor`의 보기 코드(refill: `monitor.js`·`serve.py`·`compare.py`의 refill 부분)는 원하면 따로 정리한다.
`experiments/` 폴더 자체와 이 README는 남긴다.
