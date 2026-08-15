# 계획 1 — 계약 + 데이터 파이프라인 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 산출물 스키마를 고정하고, 외통위 회의록 87건과 외교부 브리핑, 회기·일정 데이터를 공식 Open API로 수집해 검증된 중간 산출물(JSONL + 임베딩)까지 만든다.

**Architecture:** 각 단계는 순수 함수 + 파일 경계로 분리한다. 단계마다 JSONL을 입력받아 JSONL을 내보내고 `stage_meta`(입력 해시·코드 버전·실행 시각·행수)를 붙인다. 게이트 실패 시 다음 단계로 넘어가지 않고 `exit 1`. DB·Docker·백엔드 서버를 쓰지 않는다.

**Tech Stack:** Python 3.12 · requests · pymupdf · numpy · jsonschema · pytest · OpenAI embeddings

## Global Constraints

- 설계 문서: `docs/superpowers/specs/2026-08-14-agenda-entry-timeline-design.md` — 충돌 시 스펙이 우선한다.
- **스크래핑 금지.** 모든 수집은 공식 Open API를 쓴다. 예외: 외교부 브리핑 API 장애 시 폴백(이 계획 범위 밖).
- **조용한 유실 금지.** 어느 단계든 결측·파싱 실패가 생기면 파일에 기록하고 `exit 1`.
- **비밀값은 `.env`에서만 읽는다.** 코드에 키를 넣지 않는다. `.env`는 `.gitignore`에 넣고 `.env.example`만 커밋한다.
- 열린국회정보 키 환경변수명: `OPEN_ASSEMBLY` (이미 발급됨, 32자)
- 공공데이터포털 키 환경변수명: `DATA_GO_KR` (**사용자가 활용신청해야 함** — Task 7 전까지 필요)
- OpenAI 키 환경변수명: `OPENAI_API_KEY`
- 열린국회정보 API 공통 응답: 성공은 `{서비스명: [{"head":[{"list_total_count":N},{"RESULT":{"CODE":"INFO-000",...}}]},{"row":[...]}]}`, 실패는 `{"RESULT":{"CODE":"...","MESSAGE":"..."}}`
- `ERACO` 인자는 `제22대` 형식이어야 한다. `22`는 "해당하는 데이터가 없습니다"를 반환한다.
- 외통위 `DEPT_CD` = `9700409`, `COMM_NAME`/`CMIT_NM` 부분일치 검색어 = `외교통일`
- 인코딩은 전부 UTF-8. Windows 콘솔 출력 시 `sys.stdout.reconfigure(encoding="utf-8")`.
- 커밋 메시지는 한국어 본문 + Conventional Commits 접두사(`feat:`, `test:`, `chore:`).

---

## File Structure

| 파일 | 책임 |
|---|---|
| `schema/timeline.schema.json` | 최종 산출물 계약. 출처 없는 branch를 거부한다 |
| `fixtures/timeline.sample.json` | 계약 예시. 프론트(계획 3)가 이것만 보고 시작한다 |
| `pipeline/config.py` | 상수 단일 출처 — 엔드포인트, 위원회 코드, 경로 |
| `pipeline/stage.py` | `stage_meta` 생성·검증, JSONL 읽기/쓰기 |
| `pipeline/assembly_api.py` | 열린국회정보 HTTP 클라이언트 (페이징·오류 처리) |
| `pipeline/meeting_norm.py` | 3종 회의록 응답을 하나의 스키마로 정규화 + dedup |
| `pipeline/title_parse.py` | `TITLE` 문자열 → 대수·회기·차수·유형·날짜 |
| `pipeline/fetch_nk.py` | 회의록 3종 수집 실행 스크립트 |
| `pipeline/download_pdf.py` | `pdf_url` → `data/raw/*.pdf` |
| `pipeline/extract.py` | PDF → `pages.jsonl` |
| `pipeline/speaker_parse.py` | 페이지 텍스트 → 발언 턴 (순수 함수) |
| `pipeline/parse.py` | 턴 파싱 실행 + 화자 미상 게이트 |
| `pipeline/briefing_parse.py` | 브리핑 HTML → 섹션·질의응답 분리 (순수 함수) |
| `pipeline/fetch_gov.py` | 외교부 브리핑 API 수집 실행 스크립트 |
| `pipeline/calendar_calc.py` | 회기·개회일·결측 구간 산출 (순수 함수) |
| `pipeline/calendar.py` | 회기·일정 수집 실행 스크립트 |
| `pipeline/embed.py` | 임베딩 생성 → `embeddings.npy` |
| `pipeline/run.py` | 단계 오케스트레이션 |

순수 함수(`*_norm.py`, `*_parse.py`, `*_calc.py`)와 I/O 실행 스크립트(`fetch_*.py`)를 분리한다. 테스트는 순수 함수에만 건다 — 네트워크 없이 CI에서 돈다.

---

## Task 1: 프로젝트 골격과 산출물 계약

**Files:**
- Create: `.gitignore`, `.env.example`, `requirements.txt`, `pytest.ini`
- Create: `schema/timeline.schema.json`
- Create: `fixtures/timeline.sample.json`
- Create: `pipeline/config.py`
- Test: `tests/test_schema.py`

**Interfaces:**
- Consumes: 없음 (첫 태스크)
- Produces: `schema/timeline.schema.json`(계획 3의 계약), `pipeline/config.py`의 상수 — `ENDPOINTS: dict[str,str]`, `WTW_DEPT_CD: str`, `WTW_NAME: str`, `ERACO_22: str`, `DAE_NUM_22: str`, `DATA_DIR: Path`, `RAW_DIR: Path`, `INTERIM_DIR: Path`

- [ ] **Step 1: 저장소 초기화와 기본 파일 생성**

```bash
cd /c/international_relations
git init
python -m venv .venv
```

`.gitignore`:

```
.venv/
__pycache__/
*.pyc
.env
data/raw/
data/interim/
data/embeddings.npy
cache/
node_modules/
web/dist/
.pytest_cache/
```

`.env.example`:

```
OPEN_ASSEMBLY=
DATA_GO_KR=
OPENAI_API_KEY=
```

`requirements.txt`:

```
requests==2.32.3
pymupdf==1.24.10
numpy==2.1.1
jsonschema==4.23.0
python-dotenv==1.0.1
openai==1.54.3
pytest==8.3.3
```

`pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -q
```

- [ ] **Step 2: `pipeline/config.py` 작성**

```python
"""상수 단일 출처. 엔드포인트·코드·경로를 여기서만 정의한다."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
CACHE_DIR = ROOT / "cache"

ASSEMBLY_BASE = "https://open.assembly.go.kr/portal/openapi"

# 회의록 3종 — 유형별로 엔드포인트가 다르다 (스펙 5-3)
ENDPOINTS = {
    "standing": "ncwgseseafwbuheph",      # 상임위 전체회의
    "audit": "VCONFAPIGCONFLIST",         # 국정감사
    "confirm": "VCONFCFRMCONFLIST",       # 인사청문회
    "subcmt": "VCONFSUBCCONFLIST",        # 소위원회 (외통위 0건, 결측 확인용)
    "hearing": "VCONFPHCONFLIST",         # 공청회 (외통위 0건, 결측 확인용)
    "session": "BILLSESSPROD",            # 회기정보
    "schedule": "ALLSCHEDULE",            # 국회일정 통합
}

WTW_DEPT_CD = "9700409"      # 외교통일위원회
WTW_NAME = "외교통일"          # 부분일치 검색어
ERACO_22 = "제22대"           # '22' 는 데이터 없음을 반환한다
DAE_NUM_22 = "22"

MOFA_BRIEFING_ID = "15141796"
MOFA_PRESS_ID = "15141564"

PIPELINE_VERSION = "1.0.0"
```

- [ ] **Step 3: `schema/timeline.schema.json` 작성**

출처 없는 `branch`를 거부하는 것이 이 스키마의 핵심 목적이다.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "agenda entry timeline",
  "type": "object",
  "required": ["meta", "corpora", "sessions", "meetings", "briefings", "issues"],
  "additionalProperties": false,
  "properties": {
    "meta": {
      "type": "object",
      "required": ["generated_at", "pipeline_version", "precision", "recall"],
      "properties": {
        "generated_at": {"type": "string"},
        "pipeline_version": {"type": "string"},
        "precision": {"type": "number", "minimum": 0, "maximum": 1},
        "recall": {"type": "number", "minimum": 0, "maximum": 1}
      }
    },
    "corpora": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["axis", "start", "end", "doc_count"],
        "properties": {
          "axis": {"enum": ["nk", "gov"]},
          "start": {"type": "string"},
          "end": {"type": "string"},
          "doc_count": {"type": "integer", "minimum": 0}
        }
      }
    },
    "sessions": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["kind", "start", "end"],
        "properties": {
          "kind": {"enum": ["session", "committee_open", "audit", "budget", "minutes_missing"]},
          "start": {"type": "string"},
          "end": {"type": "string"},
          "label": {"type": "string"}
        }
      }
    },
    "meetings": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["conf_id", "date", "title", "meeting_type", "pdf_url"],
        "properties": {
          "conf_id": {"type": "string"},
          "date": {"type": "string"},
          "title": {"type": "string"},
          "meeting_type": {"type": "string"},
          "pdf_url": {"type": "string", "minLength": 1},
          "agenda": {"type": "array", "items": {"type": "string"}}
        }
      }
    },
    "briefings": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["briefing_id", "date", "url"],
        "properties": {
          "briefing_id": {"type": "string"},
          "date": {"type": "string"},
          "url": {"type": "string", "minLength": 1}
        }
      }
    },
    "issues": {
      "type": "array",
      "items": {"$ref": "#/$defs/issue"}
    }
  },
  "$defs": {
    "evidence": {
      "type": "object",
      "required": ["excerpt", "source_url"],
      "properties": {
        "excerpt": {"type": "string", "minLength": 1},
        "speaker": {"type": "string"},
        "page": {"type": "integer"},
        "source_url": {"type": "string", "minLength": 1}
      }
    },
    "branch": {
      "type": "object",
      "required": ["date", "kind", "verified", "evidence"],
      "additionalProperties": false,
      "properties": {
        "date": {"type": "string"},
        "kind": {"enum": ["core", "mention", "opening", "qa"]},
        "verified": {"type": "boolean"},
        "evidence": {"$ref": "#/$defs/evidence"}
      }
    },
    "axis_result": {
      "type": "object",
      "required": ["status", "observable_count", "branches"],
      "properties": {
        "status": {"enum": ["discussed", "not_found", "unobservable"]},
        "days_to_first": {"type": ["integer", "null"]},
        "meetings_to_first": {"type": ["integer", "null"]},
        "observable_count": {"type": "integer", "minimum": 0},
        "branches": {"type": "array", "items": {"$ref": "#/$defs/branch"}}
      }
    },
    "issue": {
      "type": "object",
      "required": ["issue_id", "title", "event_date", "date_type", "source_url", "description", "nk", "gov"],
      "properties": {
        "issue_id": {"type": "string"},
        "title": {"type": "string"},
        "event_date": {"type": "string"},
        "date_type": {"enum": ["발표", "서명", "발효", "공표", "개시"]},
        "source_url": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "nk": {"$ref": "#/$defs/axis_result"},
        "gov": {"$ref": "#/$defs/axis_result"},
        "gap_gov_to_nk": {"type": ["integer", "null"]},
        "pre_event": {"type": "array", "items": {"$ref": "#/$defs/branch"}}
      }
    }
  }
}
```

- [ ] **Step 4: `fixtures/timeline.sample.json` 작성 (수기 가짜 데이터 2건)**

`discussed` 1건과 `unobservable` 1건을 손으로 채운다. 계획 3의 프론트가 이 파일만 보고 시작한다.

```json
{
  "meta": {
    "generated_at": "2026-08-14T00:00:00+09:00",
    "pipeline_version": "1.0.0",
    "precision": 0.0,
    "recall": 0.0
  },
  "corpora": [
    {"axis": "nk", "start": "2024-07-17", "end": "2026-05-20", "doc_count": 87},
    {"axis": "gov", "start": "2024-05-30", "end": "2026-08-13", "doc_count": 230}
  ],
  "sessions": [
    {"kind": "session", "start": "2024-09-02", "end": "2024-12-10", "label": "제418회국회(정기회)"},
    {"kind": "committee_open", "start": "2024-07-17", "end": "2024-07-17", "label": "외통위 전체회의"},
    {"kind": "audit", "start": "2024-10-07", "end": "2024-10-25", "label": "2024 국정감사"},
    {"kind": "minutes_missing", "start": "2026-05-21", "end": "2026-08-14", "label": "회의록 미발간"}
  ],
  "meetings": [
    {
      "conf_id": "054596",
      "date": "2024-12-16",
      "title": "제22대 제419회 제2차 외교통일위원회 (2024년 12월 16일)",
      "meeting_type": "상임위원회",
      "pdf_url": "https://record.assembly.go.kr/assembly/viewer/minutes/download/pdf.do?id=52613",
      "agenda": ["1. 현안보고"]
    }
  ],
  "briefings": [
    {"briefing_id": "368859", "date": "2026-08-04", "url": "https://www.mofa.go.kr/www/brd/m_4078/view.do?seq=368859"}
  ],
  "issues": [
    {
      "issue_id": "sample-discussed",
      "title": "예시 — 논의됨",
      "event_date": "2024-12-04",
      "date_type": "발표",
      "source_url": "https://example.invalid/sample-1",
      "description": "형태 확인용 가짜 데이터. 실제 이슈가 아니다.",
      "nk": {
        "status": "discussed",
        "days_to_first": 12,
        "meetings_to_first": 1,
        "observable_count": 5,
        "branches": [
          {
            "date": "2024-12-16",
            "kind": "core",
            "verified": true,
            "evidence": {
              "excerpt": "가짜 발췌문입니다.",
              "speaker": "홍길동 위원",
              "page": 12,
              "source_url": "https://record.assembly.go.kr/assembly/viewer/minutes/download/pdf.do?id=52613"
            }
          }
        ]
      },
      "gov": {
        "status": "discussed",
        "days_to_first": 2,
        "meetings_to_first": null,
        "observable_count": 40,
        "branches": [
          {
            "date": "2024-12-06",
            "kind": "opening",
            "verified": true,
            "evidence": {
              "excerpt": "가짜 발췌문입니다.",
              "speaker": "대변인",
              "source_url": "https://www.mofa.go.kr/www/brd/m_4078/view.do?seq=368859"
            }
          }
        ]
      },
      "gap_gov_to_nk": 10,
      "pre_event": []
    },
    {
      "issue_id": "sample-unobservable",
      "title": "예시 — 관측 불가",
      "event_date": "2026-07-01",
      "date_type": "발표",
      "source_url": "https://example.invalid/sample-2",
      "description": "회의록 발간 시차 구간에 발생한 가짜 이벤트.",
      "nk": {
        "status": "unobservable",
        "days_to_first": null,
        "meetings_to_first": null,
        "observable_count": 0,
        "branches": []
      },
      "gov": {
        "status": "discussed",
        "days_to_first": 1,
        "meetings_to_first": null,
        "observable_count": 12,
        "branches": [
          {
            "date": "2026-07-02",
            "kind": "qa",
            "verified": true,
            "evidence": {
              "excerpt": "가짜 발췌문입니다.",
              "speaker": "OO일보 기자",
              "source_url": "https://www.mofa.go.kr/www/brd/m_4078/view.do?seq=368859"
            }
          }
        ]
      },
      "gap_gov_to_nk": null,
      "pre_event": []
    }
  ]
}
```

- [ ] **Step 5: 실패하는 테스트 작성**

`tests/test_schema.py`:

```python
import json
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schema" / "timeline.schema.json").read_text(encoding="utf-8"))
SAMPLE = json.loads((ROOT / "fixtures" / "timeline.sample.json").read_text(encoding="utf-8"))


def test_sample_fixture_validates():
    jsonschema.validate(SAMPLE, SCHEMA)


def test_branch_without_source_url_is_rejected():
    bad = json.loads(json.dumps(SAMPLE))
    del bad["issues"][0]["nk"]["branches"][0]["evidence"]["source_url"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, SCHEMA)


def test_branch_with_empty_excerpt_is_rejected():
    bad = json.loads(json.dumps(SAMPLE))
    bad["issues"][0]["nk"]["branches"][0]["evidence"]["excerpt"] = ""
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, SCHEMA)


def test_unknown_status_is_rejected():
    bad = json.loads(json.dumps(SAMPLE))
    bad["issues"][0]["nk"]["status"] = "maybe"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, SCHEMA)
```

- [ ] **Step 6: 테스트 실행 — 통과 확인**

```bash
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m pytest tests/test_schema.py -v
```

Expected: 4 passed. 실패하면 스키마와 fixture가 어긋난 것이므로 fixture를 고친다 (스키마를 느슨하게 만들지 말 것 — 출처 강제가 목적이다).

- [ ] **Step 7: 커밋**

```bash
git add .gitignore .env.example requirements.txt pytest.ini schema fixtures pipeline/config.py tests/test_schema.py
git commit -m "feat: 산출물 계약(JSON Schema)과 프로젝트 골격 추가

출처 없는 branch 를 스키마 수준에서 거부한다."
```

---

## Task 2: 단계 메타데이터와 JSONL 입출력

**Files:**
- Create: `pipeline/stage.py`
- Test: `tests/test_stage.py`

**Interfaces:**
- Consumes: `pipeline/config.PIPELINE_VERSION`
- Produces:
  - `make_stage_meta(stage: str, inputs: list[Path], row_count: int) -> dict`
  - `write_jsonl(path: Path, rows: list[dict], meta: dict) -> None` — 첫 줄에 `{"_stage_meta": ...}`, 이후 각 행
  - `read_jsonl(path: Path) -> tuple[dict, list[dict]]` — `(meta, rows)`
  - `fail(msg: str) -> NoReturn` — stderr 출력 후 `sys.exit(1)`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_stage.py`:

```python
import json
from pathlib import Path

import pytest

from pipeline.stage import fail, make_stage_meta, read_jsonl, write_jsonl


def test_meta_has_required_keys(tmp_path):
    src = tmp_path / "in.jsonl"
    src.write_text("hello", encoding="utf-8")
    meta = make_stage_meta("extract", [src], 3)
    assert meta["stage"] == "extract"
    assert meta["row_count"] == 3
    assert meta["pipeline_version"]
    assert meta["run_at"]
    assert len(meta["input_hashes"][str(src)]) == 64


def test_write_then_read_roundtrip(tmp_path):
    out = tmp_path / "out.jsonl"
    rows = [{"a": 1}, {"a": 2}]
    write_jsonl(out, rows, make_stage_meta("t", [], len(rows)))
    meta, got = read_jsonl(out)
    assert got == rows
    assert meta["stage"] == "t"


def test_read_rejects_row_count_mismatch(tmp_path):
    out = tmp_path / "bad.jsonl"
    rows = [{"a": 1}]
    write_jsonl(out, rows, make_stage_meta("t", [], 99))
    with pytest.raises(ValueError, match="행수 불일치"):
        read_jsonl(out)


def test_fail_exits_nonzero():
    with pytest.raises(SystemExit) as e:
        fail("terminal")
    assert e.value.code == 1
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
.venv/Scripts/python -m pytest tests/test_stage.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.stage'`

- [ ] **Step 3: 최소 구현**

`pipeline/stage.py`:

```python
"""단계 간 계약: JSONL + stage_meta. 조용한 유실을 막는 것이 목적이다."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

from pipeline.config import PIPELINE_VERSION


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def make_stage_meta(stage: str, inputs: list[Path], row_count: int) -> dict:
    return {
        "stage": stage,
        "pipeline_version": PIPELINE_VERSION,
        "run_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "row_count": row_count,
        "input_hashes": {str(p): _sha256(p) for p in inputs},
    }


def write_jsonl(path: Path, rows: list[dict], meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"_stage_meta": meta}, ensure_ascii=False) + "\n")
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> tuple[dict, list[dict]]:
    with path.open("r", encoding="utf-8") as f:
        first = json.loads(f.readline())
        if "_stage_meta" not in first:
            raise ValueError(f"{path}: 첫 줄에 _stage_meta 가 없다")
        meta = first["_stage_meta"]
        rows = [json.loads(line) for line in f if line.strip()]
    if meta["row_count"] != len(rows):
        raise ValueError(f"{path}: 행수 불일치 meta={meta['row_count']} actual={len(rows)}")
    return meta, rows


def fail(msg: str) -> NoReturn:
    print(f"[FAIL] {msg}", file=sys.stderr)
    sys.exit(1)
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
.venv/Scripts/python -m pytest tests/test_stage.py -v
```

Expected: 4 passed

- [ ] **Step 5: 커밋**

```bash
git add pipeline/stage.py tests/test_stage.py
git commit -m "feat: 단계 메타데이터와 JSONL 입출력

행수 불일치를 읽기 시점에 잡아 조용한 유실을 막는다."
```

---

## Task 3: 회의명 파서

**Files:**
- Create: `pipeline/title_parse.py`
- Test: `tests/test_title_parse.py`

**Interfaces:**
- Consumes: 없음 (순수 함수)
- Produces: `parse_title(title: str) -> dict` — 키 `dae`(int|None), `sess`(int|None), `dgr`(int|None), `committee`(str|None), `date`(str|None, `YYYY-MM-DD`)

- [ ] **Step 1: 실패하는 테스트 작성**

실제 API 응답에서 관측한 형식을 그대로 쓴다.

`tests/test_title_parse.py`:

```python
from pipeline.title_parse import parse_title


def test_standard_title():
    got = parse_title("제22대 제419회 제2차 외교통일위원회 (2024년 12월 16일)")
    assert got == {
        "dae": 22, "sess": 419, "dgr": 2,
        "committee": "외교통일위원회", "date": "2024-12-16",
    }


def test_single_digit_day_is_zero_padded():
    got = parse_title("제22대 제418회 제1차 외교통일위원회 (2024년 9월 3일)")
    assert got["date"] == "2024-09-03"


def test_zero_degree_is_parsed():
    got = parse_title("제10대국회 제101회 0차 국회본회의 1979년 03월 19일 ")
    assert got["sess"] == 101
    assert got["dgr"] == 0
    assert got["date"] == "1979-03-19"


def test_unparseable_returns_none_fields_not_exception():
    got = parse_title("알 수 없는 형식")
    assert got == {"dae": None, "sess": None, "dgr": None, "committee": None, "date": None}


def test_empty_string():
    got = parse_title("")
    assert got["date"] is None
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
.venv/Scripts/python -m pytest tests/test_title_parse.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.title_parse'`

- [ ] **Step 3: 최소 구현**

`pipeline/title_parse.py`:

```python
"""회의명 문자열 파서. 예외를 던지지 않고 못 읽은 필드는 None 으로 둔다."""
from __future__ import annotations

import re

_DAE = re.compile(r"제(\d+)대")
_SESS = re.compile(r"제(\d+)회")
_DGR = re.compile(r"제?(\d+)차")
_CMIT = re.compile(r"([가-힣]+위원회)")
_DATE = re.compile(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일")


def _first_int(pattern: re.Pattern[str], text: str) -> int | None:
    m = pattern.search(text)
    return int(m.group(1)) if m else None


def parse_title(title: str) -> dict:
    text = title or ""
    date = None
    m = _DATE.search(text)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        date = f"{y:04d}-{mo:02d}-{d:02d}"
    cm = _CMIT.search(text)
    return {
        "dae": _first_int(_DAE, text),
        "sess": _first_int(_SESS, text),
        "dgr": _first_int(_DGR, text),
        "committee": cm.group(1) if cm else None,
        "date": date,
    }
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
.venv/Scripts/python -m pytest tests/test_title_parse.py -v
```

Expected: 5 passed

- [ ] **Step 5: 커밋**

```bash
git add pipeline/title_parse.py tests/test_title_parse.py
git commit -m "test: 회의명 파서 추가

대수·회기·차수·위원회·날짜를 추출한다. 실패 시 예외 대신 None."
```

---

## Task 4: 회의록 3종 정규화와 병합

**Files:**
- Create: `pipeline/meeting_norm.py`
- Test: `tests/test_meeting_norm.py`

**Interfaces:**
- Consumes: `pipeline.title_parse.parse_title`
- Produces:
  - `normalize_standing(row: dict) -> dict`
  - `normalize_vconf(row: dict) -> dict` (국정감사·인사청문회·소위·공청회 공통 형식)
  - `merge_meetings(groups: list[list[dict]]) -> list[dict]` — `conf_id` 기준 dedup, `agenda` 합집합, 날짜 오름차순

**정규화 스키마 (하위 태스크가 이 키만 쓴다):**
`conf_id`, `date`, `title`, `meeting_type`, `pdf_url`, `agenda`(list[str]), `sess`, `dgr`, `source_api`

두 API의 필드명이 다르다는 것이 이 태스크의 존재 이유다 — 상임위는 `CONF_DATE`/`COMM_NAME`/`PDF_LINK_URL`/`SUB_NAME`, 나머지는 `CONF_DT`/`CMIT_NM`/`DOWN_URL`/(안건 없음).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_meeting_norm.py`:

```python
from pipeline.meeting_norm import merge_meetings, normalize_standing, normalize_vconf

STANDING = {
    "CONFER_NUM": "52613",
    "TITLE": "제22대 제419회 제2차 외교통일위원회 (2024년 12월 16일)",
    "CLASS_NAME": "상임위원회",
    "DAE_NUM": "22",
    "COMM_NAME": "외교통일위원회",
    "CONF_DATE": "2024-12-16",
    "SUB_NAME": "1. 현안보고",
    "PDF_LINK_URL": "https://record.assembly.go.kr/assembly/viewer/minutes/download/pdf.do?id=52613",
    "DEPT_CD": "9700409",
    "CONF_ID": "054596",
}

VCONF = {
    "CONF_ID": "060001",
    "ERACO": "제22대",
    "SESS": "제418회",
    "DGR": "제3차",
    "CONF_DT": "2024-10-08",
    "CONF_KND": "국정감사",
    "CMIT_CD": "9700409",
    "CMIT_NM": "외교통일위원회",
    "DOWN_URL": "https://record.assembly.go.kr/assembly/viewer/minutes/download/pdf.do?id=99999",
}


def test_normalize_standing_maps_fields():
    got = normalize_standing(STANDING)
    assert got["conf_id"] == "054596"
    assert got["date"] == "2024-12-16"
    assert got["meeting_type"] == "상임위원회"
    assert got["pdf_url"].endswith("id=52613")
    assert got["agenda"] == ["1. 현안보고"]
    assert got["sess"] == 419
    assert got["source_api"] == "standing"


def test_normalize_vconf_maps_different_field_names():
    got = normalize_vconf(VCONF, source_api="audit")
    assert got["conf_id"] == "060001"
    assert got["date"] == "2024-10-08"
    assert got["meeting_type"] == "국정감사"
    assert got["pdf_url"].endswith("id=99999")
    assert got["agenda"] == []
    assert got["sess"] == 418
    assert got["dgr"] == 3
    assert got["source_api"] == "audit"


def test_merge_dedups_by_conf_id_and_unions_agenda():
    a = normalize_standing(STANDING)
    b = normalize_standing({**STANDING, "SUB_NAME": "2. 기금운용계획안"})
    merged = merge_meetings([[a, b]])
    assert len(merged) == 1
    assert merged[0]["agenda"] == ["1. 현안보고", "2. 기금운용계획안"]


def test_merge_sorts_by_date_ascending():
    a = normalize_standing(STANDING)
    b = normalize_vconf(VCONF, source_api="audit")
    merged = merge_meetings([[a], [b]])
    assert [m["date"] for m in merged] == ["2024-10-08", "2024-12-16"]


def test_merge_across_apis_keeps_both_types():
    merged = merge_meetings([[normalize_standing(STANDING)], [normalize_vconf(VCONF, source_api="audit")]])
    assert {m["meeting_type"] for m in merged} == {"상임위원회", "국정감사"}


def test_missing_pdf_url_raises():
    import pytest
    bad = {**STANDING, "PDF_LINK_URL": ""}
    with pytest.raises(ValueError, match="pdf_url"):
        normalize_standing(bad)
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
.venv/Scripts/python -m pytest tests/test_meeting_norm.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.meeting_norm'`

- [ ] **Step 3: 최소 구현**

`pipeline/meeting_norm.py`:

```python
"""회의록 3종 응답을 하나의 스키마로 정규화한다.

상임위(ncwgseseafwbuheph)와 나머지(VCONF*)는 필드명이 다르다.
"""
from __future__ import annotations

import re

from pipeline.title_parse import parse_title

_NUM = re.compile(r"(\d+)")


def _int_or_none(value) -> int | None:
    if value is None:
        return None
    m = _NUM.search(str(value))
    return int(m.group(1)) if m else None


def _require_pdf(url: str | None, conf_id: str) -> str:
    if not url:
        raise ValueError(f"pdf_url 누락: conf_id={conf_id}")
    return url


def normalize_standing(row: dict) -> dict:
    parsed = parse_title(row.get("TITLE", ""))
    conf_id = str(row.get("CONF_ID") or row.get("CONFER_NUM") or "")
    agenda = [row["SUB_NAME"]] if row.get("SUB_NAME") else []
    return {
        "conf_id": conf_id,
        "date": row.get("CONF_DATE") or parsed["date"],
        "title": row.get("TITLE", ""),
        "meeting_type": row.get("CLASS_NAME") or "상임위원회",
        "pdf_url": _require_pdf(row.get("PDF_LINK_URL"), conf_id),
        "agenda": agenda,
        "sess": parsed["sess"],
        "dgr": parsed["dgr"],
        "source_api": "standing",
    }


def normalize_vconf(row: dict, source_api: str) -> dict:
    conf_id = str(row.get("CONF_ID") or "")
    title = " ".join(
        str(x) for x in (row.get("ERACO"), row.get("SESS"), row.get("DGR"),
                         row.get("CMIT_NM"), row.get("CONF_DT")) if x
    )
    return {
        "conf_id": conf_id,
        "date": row.get("CONF_DT"),
        "title": title,
        "meeting_type": row.get("CONF_KND") or source_api,
        "pdf_url": _require_pdf(row.get("DOWN_URL"), conf_id),
        "agenda": [],
        "sess": _int_or_none(row.get("SESS")),
        "dgr": _int_or_none(row.get("DGR")),
        "source_api": source_api,
    }


def merge_meetings(groups: list[list[dict]]) -> list[dict]:
    by_id: dict[str, dict] = {}
    for group in groups:
        for row in group:
            key = row["conf_id"]
            if key not in by_id:
                by_id[key] = {**row, "agenda": list(row["agenda"])}
                continue
            for item in row["agenda"]:
                if item not in by_id[key]["agenda"]:
                    by_id[key]["agenda"].append(item)
    return sorted(by_id.values(), key=lambda r: (r["date"] or "", r["conf_id"]))
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
.venv/Scripts/python -m pytest tests/test_meeting_norm.py -v
```

Expected: 6 passed

- [ ] **Step 5: 커밋**

```bash
git add pipeline/meeting_norm.py tests/test_meeting_norm.py
git commit -m "feat: 회의록 3종 정규화·병합

상임위와 VCONF 계열의 필드명 차이를 흡수하고 conf_id 로 dedup 한다."
```

---

## Task 5: 열린국회정보 클라이언트와 회의록 수집

**Files:**
- Create: `pipeline/assembly_api.py`
- Create: `pipeline/fetch_nk.py`
- Test: `tests/test_assembly_api.py`

**Interfaces:**
- Consumes: `pipeline.config.ENDPOINTS`, `pipeline.stage.write_jsonl`, `pipeline.meeting_norm.*`
- Produces:
  - `parse_response(payload: dict) -> tuple[int, list[dict]]` — `(list_total_count, rows)`; 오류 응답은 `ApiError` 발생. "해당하는 데이터가 없습니다"는 `(0, [])`로 처리
  - `class ApiError(RuntimeError)`
  - `fetch_all(endpoint: str, params: dict, key: str, page_size: int = 100) -> list[dict]`
  - 실행 산출물: `data/interim/meetings.jsonl`

- [ ] **Step 1: 실패하는 테스트 작성**

실제 관측한 응답 모양을 그대로 쓴다.

`tests/test_assembly_api.py`:

```python
import pytest

from pipeline.assembly_api import ApiError, parse_response

OK = {
    "ncwgseseafwbuheph": [
        {"head": [{"list_total_count": 276},
                  {"RESULT": {"CODE": "INFO-000", "MESSAGE": "정상 처리되었습니다."}}]},
        {"row": [{"CONF_ID": "1"}, {"CONF_ID": "2"}]},
    ]
}
EMPTY = {"RESULT": {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다."}}
BAD_SERVICE = {"RESULT": {"CODE": "ERROR-310", "MESSAGE": "해당하는 서비스를 찾을 수 없습니다."}}
MISSING_ARG = {"RESULT": {"CODE": "ERROR-300", "MESSAGE": "필수 값이 누락되어 있습니다."}}


def test_parse_ok():
    total, rows = parse_response(OK)
    assert total == 276
    assert [r["CONF_ID"] for r in rows] == ["1", "2"]


def test_no_data_is_empty_not_error():
    assert parse_response(EMPTY) == (0, [])


def test_unknown_service_raises():
    with pytest.raises(ApiError, match="ERROR-310"):
        parse_response(BAD_SERVICE)


def test_missing_required_arg_raises():
    with pytest.raises(ApiError, match="ERROR-300"):
        parse_response(MISSING_ARG)
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
.venv/Scripts/python -m pytest tests/test_assembly_api.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.assembly_api'`

- [ ] **Step 3: 최소 구현**

`pipeline/assembly_api.py`:

```python
"""열린국회정보 Open API 클라이언트. 요청제한은 없지만 예의상 간격을 둔다."""
from __future__ import annotations

import time

import requests

from pipeline.config import ASSEMBLY_BASE

NO_DATA_CODE = "INFO-200"
OK_CODE = "INFO-000"


class ApiError(RuntimeError):
    pass


def parse_response(payload: dict) -> tuple[int, list[dict]]:
    if "RESULT" in payload:
        result = payload["RESULT"]
        if result.get("CODE") == NO_DATA_CODE:
            return 0, []
        raise ApiError(f"{result.get('CODE')}: {result.get('MESSAGE')}")
    service = next(iter(payload))
    body = payload[service]
    head = body[0]["head"]
    total = head[0]["list_total_count"]
    code = head[1]["RESULT"]["CODE"]
    if code != OK_CODE:
        raise ApiError(f"{code}: {head[1]['RESULT'].get('MESSAGE')}")
    return total, body[1]["row"]


def fetch_all(endpoint: str, params: dict, key: str, page_size: int = 100,
              delay: float = 0.2, max_pages: int = 200) -> list[dict]:
    rows: list[dict] = []
    session = requests.Session()
    session.headers.update({"User-Agent": "agenda-entry-timeline/1.0"})
    for page in range(1, max_pages + 1):
        query = {"KEY": key, "Type": "json", "pIndex": page, "pSize": page_size, **params}
        resp = session.get(f"{ASSEMBLY_BASE}/{endpoint}", params=query, timeout=30)
        resp.raise_for_status()
        _, batch = parse_response(resp.json())
        rows.extend(batch)
        if len(batch) < page_size:
            return rows
        time.sleep(delay)
    raise ApiError(f"{endpoint}: max_pages({max_pages}) 초과 — 페이징이 끝나지 않는다")
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
.venv/Scripts/python -m pytest tests/test_assembly_api.py -v
```

Expected: 4 passed

- [ ] **Step 5: 수집 실행 스크립트 작성**

`pipeline/fetch_nk.py`:

```python
"""외통위 회의록 3종을 수집해 하나의 목록으로 합친다.

  python -m pipeline.fetch_nk
"""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

from pipeline.assembly_api import fetch_all
from pipeline.config import (DAE_NUM_22, ENDPOINTS, ERACO_22, INTERIM_DIR,
                             WTW_DEPT_CD, WTW_NAME)
from pipeline.meeting_norm import merge_meetings, normalize_standing, normalize_vconf
from pipeline.stage import fail, make_stage_meta, write_jsonl

# 상임위 API 는 CONF_DATE 가 필수이고 부분일치라 연도로 훑는다.
YEARS = ["2024", "2025", "2026"]
VCONF_SOURCES = {"audit": ENDPOINTS["audit"], "confirm": ENDPOINTS["confirm"],
                 "subcmt": ENDPOINTS["subcmt"], "hearing": ENDPOINTS["hearing"]}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv()
    key = os.environ.get("OPEN_ASSEMBLY")
    if not key:
        fail(".env 에 OPEN_ASSEMBLY 키가 없다")

    groups: list[list[dict]] = []
    counts: dict[str, int] = {}

    standing: list[dict] = []
    for year in YEARS:
        raw = fetch_all(ENDPOINTS["standing"], {
            "DAE_NUM": DAE_NUM_22, "CONF_DATE": year, "COMM_NAME": WTW_NAME}, key)
        standing.extend(normalize_standing(r) for r in raw)
    groups.append(standing)
    counts["standing"] = len({r["conf_id"] for r in standing})

    for name, endpoint in VCONF_SOURCES.items():
        raw = fetch_all(endpoint, {"ERACO": ERACO_22}, key)
        rows = [normalize_vconf(r, source_api=name) for r in raw
                if WTW_NAME in str(r.get("CMIT_NM", "")) or str(r.get("CMIT_CD")) == WTW_DEPT_CD]
        groups.append(rows)
        counts[name] = len({r["conf_id"] for r in rows})

    meetings = merge_meetings(groups)
    for name, n in counts.items():
        print(f"  {name:10} {n:4}건")
    print(f"  병합 후      {len(meetings):4}건  {meetings[0]['date']} ~ {meetings[-1]['date']}")

    if counts["standing"] == 0:
        fail("상임위 회의록이 0건이다 — 인자나 키를 확인하라")
    if counts["audit"] == 0:
        fail("국정감사 회의록이 0건이다 — ERACO 형식(제22대)을 확인하라")

    out = INTERIM_DIR / "meetings.jsonl"
    write_jsonl(out, meetings, make_stage_meta("fetch_nk", [], len(meetings)))
    print(f"[OK] {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: 실제 수집 실행 — 87건 확인**

```bash
.venv/Scripts/python -m pipeline.fetch_nk
```

Expected: `standing 54` / `audit 31` / `confirm 2` / `subcmt 0` / `hearing 0` / `병합 후 87건  2024-07-17 ~ 2026-05-20`

숫자가 다르면 **멈추고 원인을 적는다.** 스펙 5-3의 실측값과 다르면 API 쪽이 바뀐 것이므로 스펙을 갱신해야 한다 — 코드를 숫자에 맞추지 말 것.

- [ ] **Step 7: 커밋**

```bash
git add pipeline/assembly_api.py pipeline/fetch_nk.py tests/test_assembly_api.py
git commit -m "feat: 외통위 회의록 3종 수집

상임위 54 + 국정감사 31 + 인사청문회 2 = 87건.
국정감사가 상임위 API 에 없다는 것이 이 태스크의 핵심."
```

---

## Task 6: PDF 다운로드와 텍스트 추출

**Files:**
- Create: `pipeline/download_pdf.py`
- Create: `pipeline/extract.py`
- Test: `tests/test_extract.py`

**Interfaces:**
- Consumes: `data/interim/meetings.jsonl`
- Produces:
  - `pages_from_pdf(path: Path) -> list[dict]` — 각 `{"page": int, "text": str}`
  - `check_loss(pages: list[dict]) -> list[int]` — 텍스트가 빈 페이지 번호 목록
  - 실행 산출물: `data/raw/{conf_id}.pdf`, `data/interim/pages.jsonl`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_extract.py`:

```python
import fitz
import pytest

from pipeline.extract import check_loss, pages_from_pdf


def _make_pdf(tmp_path, texts):
    doc = fitz.open()
    for t in texts:
        page = doc.new_page()
        if t:
            page.insert_text((72, 72), t, fontname="helv", fontsize=12)
    path = tmp_path / "sample.pdf"
    doc.save(str(path))
    doc.close()
    return path


def test_pages_are_numbered_from_one(tmp_path):
    path = _make_pdf(tmp_path, ["alpha", "beta"])
    pages = pages_from_pdf(path)
    assert [p["page"] for p in pages] == [1, 2]
    assert "alpha" in pages[0]["text"]


def test_check_loss_reports_empty_pages(tmp_path):
    path = _make_pdf(tmp_path, ["alpha", "", "gamma"])
    pages = pages_from_pdf(path)
    assert check_loss(pages) == [2]


def test_check_loss_empty_when_all_pages_have_text(tmp_path):
    path = _make_pdf(tmp_path, ["a", "b"])
    assert check_loss(pages_from_pdf(path)) == []


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        pages_from_pdf(tmp_path / "nope.pdf")
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
.venv/Scripts/python -m pytest tests/test_extract.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.extract'`

- [ ] **Step 3: 최소 구현**

`pipeline/download_pdf.py`:

```python
"""회의록 PDF 를 내려받는다. 증분 모드이며 %PDF 매직 바이트를 검사한다."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import requests

from pipeline.config import INTERIM_DIR, RAW_DIR
from pipeline.stage import fail, read_jsonl


def download(url: str, dest: Path, session: requests.Session) -> bool:
    if dest.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    resp = session.get(url, timeout=120, stream=True)
    resp.raise_for_status()
    try:
        with tmp.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
        if tmp.open("rb").read(5) != b"%PDF-":
            raise ValueError("응답이 PDF 가 아니다")
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)
    return True


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    _, meetings = read_jsonl(INTERIM_DIR / "meetings.jsonl")
    session = requests.Session()
    session.headers.update({"User-Agent": "agenda-entry-timeline/1.0"})
    got = skipped = 0
    errors: list[str] = []
    for m in meetings:
        dest = RAW_DIR / f"{m['conf_id']}.pdf"
        try:
            if download(m["pdf_url"], dest, session):
                got += 1
                time.sleep(0.3)
            else:
                skipped += 1
        except Exception as exc:
            errors.append(f"{m['conf_id']}: {exc}")
    print(f"  다운로드 {got} / 기존 {skipped} / 오류 {len(errors)}")
    if errors:
        for e in errors:
            print(f"  [ERR] {e}")
        fail(f"PDF 다운로드 실패 {len(errors)}건 — 조용히 넘어가지 않는다")


if __name__ == "__main__":
    main()
```

`pipeline/extract.py`:

```python
"""PDF → 페이지 텍스트. 손실률 0 이 게이트다."""
from __future__ import annotations

import sys
from pathlib import Path

import fitz

from pipeline.config import INTERIM_DIR, RAW_DIR
from pipeline.stage import fail, make_stage_meta, read_jsonl, write_jsonl


def pages_from_pdf(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(path)
    doc = fitz.open(str(path))
    try:
        return [{"page": i + 1, "text": doc[i].get_text().strip()} for i in range(doc.page_count)]
    finally:
        doc.close()


def check_loss(pages: list[dict]) -> list[int]:
    return [p["page"] for p in pages if not p["text"]]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    _, meetings = read_jsonl(INTERIM_DIR / "meetings.jsonl")
    rows: list[dict] = []
    losses: list[str] = []
    for m in meetings:
        path = RAW_DIR / f"{m['conf_id']}.pdf"
        pages = pages_from_pdf(path)
        empty = check_loss(pages)
        if empty:
            losses.append(f"{m['conf_id']} ({m['date']}): 빈 페이지 {empty}")
        for p in pages:
            rows.append({"conf_id": m["conf_id"], "date": m["date"], **p})
    print(f"  회의 {len(meetings)}건 / 페이지 {len(rows)}쪽")
    if losses:
        for l in losses:
            print(f"  [LOSS] {l}")
        fail(f"텍스트 없는 페이지가 있는 회의 {len(losses)}건 — 스캔 PDF 가능성. OCR 여부를 결정하라")
    out = INTERIM_DIR / "pages.jsonl"
    write_jsonl(out, rows, make_stage_meta("extract", [INTERIM_DIR / "meetings.jsonl"], len(rows)))
    print(f"[OK] {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
.venv/Scripts/python -m pytest tests/test_extract.py -v
```

Expected: 4 passed

- [ ] **Step 5: 실제 실행**

```bash
.venv/Scripts/python -m pipeline.download_pdf
.venv/Scripts/python -m pipeline.extract
```

Expected: 다운로드 87건, 페이지 수천 쪽, `[OK] data/interim/pages.jsonl`

`[LOSS]`가 나오면 그 회의록이 스캔 이미지 PDF다. **멈추고 몇 건인지 기록한다.** 소수면 해당 회의를 결측으로 표시하고 계속, 다수면 OCR 도입을 결정해야 한다 — 어느 쪽이든 사람 판단이다.

- [ ] **Step 6: 커밋**

```bash
git add pipeline/download_pdf.py pipeline/extract.py tests/test_extract.py
git commit -m "feat: PDF 다운로드와 텍스트 추출

손실률 0 을 게이트로 건다. 다운로드 실패는 exit 1."
```

---

## Task 7: 발언자 턴 파서와 품질 게이트

**Files:**
- Create: `pipeline/speaker_parse.py`
- Create: `pipeline/parse.py`
- Test: `tests/test_speaker_parse.py`

**Interfaces:**
- Consumes: `data/interim/pages.jsonl`
- Produces:
  - `split_turns(pages: list[dict]) -> list[dict]` — 각 `{"turn_index": int, "speaker": str|None, "role": str|None, "text": str, "page_start": int, "page_end": int}`
  - `unknown_ratio(turns: list[dict]) -> float`
  - 실행 산출물: `data/interim/turns.jsonl`
- 게이트: `unknown_ratio` > 0.05 이면 `exit 1`

- [ ] **Step 1: 실패하는 테스트 작성**

회의록 서식(`◯이름 위원`, `◯위원장 …`, `◯외교부장관 …`)을 대상으로 한다.

`tests/test_speaker_parse.py`:

```python
from pipeline.speaker_parse import split_turns, unknown_ratio

PAGES = [
    {"page": 1, "text": "◯위원장 김태호 의사일정을 시작하겠습니다.\n◯홍길동 위원 질의드리겠습니다.\n계속합니다."},
    {"page": 2, "text": "◯외교부장관 조현 답변드리겠습니다.\n◯홍길동 위원 감사합니다."},
]


def test_turns_are_split_by_marker():
    turns = split_turns(PAGES)
    assert len(turns) == 4
    assert turns[0]["speaker"] == "김태호"
    assert turns[0]["role"] == "위원장"
    assert turns[1]["speaker"] == "홍길동"
    assert turns[1]["role"] == "위원"


def test_multiline_text_is_joined_into_the_turn():
    turns = split_turns(PAGES)
    assert "계속합니다." in turns[1]["text"]


def test_government_role_is_captured():
    turns = split_turns(PAGES)
    assert turns[2]["role"] == "외교부장관"
    assert turns[2]["speaker"] == "조현"


def test_page_span_is_recorded():
    turns = split_turns(PAGES)
    assert turns[0]["page_start"] == 1
    assert turns[3]["page_start"] == 2


def test_turn_index_is_sequential_from_one():
    turns = split_turns(PAGES)
    assert [t["turn_index"] for t in turns] == [1, 2, 3, 4]


def test_text_before_first_marker_becomes_unknown_speaker():
    pages = [{"page": 1, "text": "머리말입니다.\n◯홍길동 위원 시작합니다."}]
    turns = split_turns(pages)
    assert turns[0]["speaker"] is None
    assert "머리말" in turns[0]["text"]


def test_unknown_ratio():
    pages = [{"page": 1, "text": "머리말입니다.\n◯홍길동 위원 시작합니다."}]
    assert unknown_ratio(split_turns(pages)) == 0.5


def test_empty_pages_give_no_turns():
    assert split_turns([]) == []
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
.venv/Scripts/python -m pytest tests/test_speaker_parse.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.speaker_parse'`

- [ ] **Step 3: 최소 구현**

`pipeline/speaker_parse.py`:

```python
"""발언 턴 파서.

전량 정확도를 목표로 하지 않는다(스펙 9-5). 최종 인용되는 발언의
발언자·쪽수만 정확하면 되고, 그것은 사람이 전수 대조한다.
"""
from __future__ import annotations

import re

# ◯ 또는 ○ 로 시작하는 발언 머리. '역할 이름' 또는 '이름 역할' 두 형태를 받는다.
_MARKER = re.compile(r"^[◯○]\s*(?P<head>[^\s]+)\s+(?P<tail>[^\s]+)")
_ROLE_FIRST = ("위원장", "부위원장", "위원장대리")


def _classify(head: str, tail: str) -> tuple[str | None, str | None]:
    if head in _ROLE_FIRST or head.endswith(("장관", "차관", "본부장", "실장", "청장", "대사")):
        return tail, head          # 역할 먼저: ◯위원장 김태호
    return head, tail              # 이름 먼저: ◯홍길동 위원


def split_turns(pages: list[dict]) -> list[dict]:
    turns: list[dict] = []
    current: dict | None = None
    for page in pages:
        for line in page["text"].split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            m = _MARKER.match(stripped)
            if m:
                speaker, role = _classify(m.group("head"), m.group("tail"))
                rest = stripped[m.end():].strip()
                current = {
                    "turn_index": len(turns) + 1,
                    "speaker": speaker,
                    "role": role,
                    "text": rest,
                    "page_start": page["page"],
                    "page_end": page["page"],
                }
                turns.append(current)
                continue
            if current is None:
                current = {
                    "turn_index": 1, "speaker": None, "role": None,
                    "text": stripped, "page_start": page["page"], "page_end": page["page"],
                }
                turns.append(current)
                continue
            current["text"] = (current["text"] + "\n" + stripped).strip()
            current["page_end"] = page["page"]
    return turns


def unknown_ratio(turns: list[dict]) -> float:
    if not turns:
        return 0.0
    return sum(1 for t in turns if t["speaker"] is None) / len(turns)
```

`pipeline/parse.py`:

```python
"""페이지 → 발언 턴. 화자 미상 비율이 게이트다."""
from __future__ import annotations

import sys
from collections import defaultdict

from pipeline.config import INTERIM_DIR
from pipeline.speaker_parse import split_turns, unknown_ratio
from pipeline.stage import fail, make_stage_meta, read_jsonl, write_jsonl

UNKNOWN_LIMIT = 0.05


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    src = INTERIM_DIR / "pages.jsonl"
    _, pages = read_jsonl(src)
    by_meeting: dict[str, list[dict]] = defaultdict(list)
    dates: dict[str, str] = {}
    for p in pages:
        by_meeting[p["conf_id"]].append(p)
        dates[p["conf_id"]] = p["date"]

    rows: list[dict] = []
    worst: list[tuple[str, float]] = []
    for conf_id, group in by_meeting.items():
        group.sort(key=lambda x: x["page"])
        turns = split_turns(group)
        ratio = unknown_ratio(turns)
        worst.append((conf_id, ratio))
        for t in turns:
            rows.append({"conf_id": conf_id, "date": dates[conf_id], **t})

    overall = sum(1 for r in rows if r["speaker"] is None) / len(rows) if rows else 0.0
    worst.sort(key=lambda x: -x[1])
    print(f"  회의 {len(by_meeting)}건 / 턴 {len(rows)}개 / 화자 미상 {overall:.1%}")
    for conf_id, ratio in worst[:5]:
        print(f"    {conf_id} {ratio:.1%}")
    if overall > UNKNOWN_LIMIT:
        fail(f"화자 미상 비율 {overall:.1%} > {UNKNOWN_LIMIT:.0%} — 파서 패턴을 보강하라")

    out = INTERIM_DIR / "turns.jsonl"
    write_jsonl(out, rows, make_stage_meta("parse", [src], len(rows)))
    print(f"[OK] {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
.venv/Scripts/python -m pytest tests/test_speaker_parse.py -v
```

Expected: 8 passed

- [ ] **Step 5: 실제 실행 — 게이트 통과 확인**

```bash
.venv/Scripts/python -m pipeline.parse
```

Expected: 화자 미상 비율이 5% 이하이고 `[OK] data/interim/turns.jsonl`

게이트에 걸리면 상위 5개 회의의 원문 PDF를 직접 열어 실제 서식을 확인하고 `_MARKER`/`_classify`를 보강한 뒤 다시 돌린다. **한계를 올려서 통과시키지 말 것.**

- [ ] **Step 6: 커밋**

```bash
git add pipeline/speaker_parse.py pipeline/parse.py tests/test_speaker_parse.py
git commit -m "feat: 발언 턴 파서와 화자 미상 게이트

전량 정확도가 아니라 인용될 발언의 정확도를 목표로 한다(스펙 9-5)."
```

---

## Task 8: 외교부 브리핑 수집과 섹션 분리

**Files:**
- Create: `pipeline/briefing_parse.py`
- Create: `pipeline/fetch_gov.py`
- Test: `tests/test_briefing_parse.py`

**Interfaces:**
- Consumes: `DATA_GO_KR` 키
- Produces:
  - `strip_html(html: str) -> str`
  - `split_sections(text: str) -> dict` — `{"opening": str, "qa": list[dict]}`, 각 qa는 `{"question": str, "answer": str, "asker": str|None}`
  - 실행 산출물: `data/interim/briefings.jsonl` — 각 `{"briefing_id", "date", "url", "opening", "qa"}`

**선행 조건:** `.env`에 `DATA_GO_KR` 키가 있어야 한다. 없으면 이 태스크를 시작하지 말고 사용자에게 활용신청을 요청한다(공공데이터포털 `15141796`, 자동승인·무료).

- [ ] **Step 1: 실패하는 테스트 작성**

실제 브리핑 원문 구조를 그대로 쓴다.

`tests/test_briefing_parse.py`:

```python
from pipeline.briefing_parse import split_sections, strip_html

RAW = """<div>I. 모두 발언<br/>
안녕하십니까? 대변인입니다.<br/>
이상입니다. 질문 주시면 답변드리겠습니다.<br/>
Ⅱ. 질의 및 응답<br/>
&lt;질문&gt; 첫 번째 질문입니다. (OO일보 김기자)<br/>
&lt;답변&gt; 첫 번째 답변입니다.<br/>
&lt;질문&gt; 두 번째 질문입니다. (△△TV 이기자)<br/>
&lt;답변&gt; 두 번째 답변입니다.</div>"""


def test_strip_html_unescapes_and_removes_tags():
    text = strip_html(RAW)
    assert "<div>" not in text
    assert "<질문>" in text


def test_opening_section_is_extracted():
    got = split_sections(strip_html(RAW))
    assert "안녕하십니까? 대변인입니다." in got["opening"]
    assert "첫 번째 질문" not in got["opening"]


def test_qa_pairs_are_split():
    got = split_sections(strip_html(RAW))
    assert len(got["qa"]) == 2
    assert got["qa"][0]["question"].startswith("첫 번째 질문")
    assert got["qa"][0]["answer"].startswith("첫 번째 답변")


def test_asker_is_extracted_from_parenthesis():
    got = split_sections(strip_html(RAW))
    assert got["qa"][0]["asker"] == "OO일보 김기자"
    assert got["qa"][1]["asker"] == "△△TV 이기자"


def test_briefing_without_qa_section():
    text = strip_html("<p>I. 모두 발언<br/>공지만 있습니다.</p>")
    got = split_sections(text)
    assert got["qa"] == []
    assert "공지만 있습니다." in got["opening"]


def test_briefing_without_any_marker_goes_to_opening():
    got = split_sections("마커 없는 본문")
    assert got["opening"] == "마커 없는 본문"
    assert got["qa"] == []
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
.venv/Scripts/python -m pytest tests/test_briefing_parse.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.briefing_parse'`

- [ ] **Step 3: 최소 구현**

`pipeline/briefing_parse.py`:

```python
"""브리핑 HTML → 섹션 분리.

'모두 발언'(정부 선제)과 '질의 및 응답'(기자 질문에 답)의 구분이 핵심이다
— 스펙 7-4. 이 구분 없이는 정부가 먼저 꺼낸 것과 물어서 답한 것이 섞인다.
"""
from __future__ import annotations

import html
import re

_TAG = re.compile(r"<[^>]+>")
_QA_HEAD = re.compile(r"[ⅡII2]\s*[.．]\s*질의\s*및\s*응답")
_OPEN_HEAD = re.compile(r"[ⅠI1]\s*[.．]\s*모두\s*발언")
_Q = re.compile(r"<질문>")
_A = re.compile(r"<답변>")
_ASKER = re.compile(r"\(([^()]{2,40})\)\s*$")


def strip_html(raw: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", raw or "", flags=re.I)
    text = _TAG.sub("", text)
    text = html.unescape(text)
    return "\n".join(line.strip() for line in text.split("\n") if line.strip())


def _parse_qa(block: str) -> list[dict]:
    pairs: list[dict] = []
    chunks = [c for c in _Q.split(block) if c.strip()]
    for chunk in chunks:
        parts = _A.split(chunk, maxsplit=1)
        question = parts[0].strip()
        answer = parts[1].strip() if len(parts) > 1 else ""
        asker = None
        m = _ASKER.search(question)
        if m:
            asker = m.group(1).strip()
            question = question[: m.start()].strip()
        pairs.append({"question": question, "answer": answer, "asker": asker})
    return pairs


def split_sections(text: str) -> dict:
    qa_match = _QA_HEAD.search(text)
    if qa_match:
        head, tail = text[: qa_match.start()], text[qa_match.end():]
    else:
        head, tail = text, ""
    open_match = _OPEN_HEAD.search(head)
    opening = head[open_match.end():].strip() if open_match else head.strip()
    return {"opening": opening, "qa": _parse_qa(tail) if tail.strip() else []}
```

`pipeline/fetch_gov.py`:

```python
"""외교부 브리핑 API 수집.

  python -m pipeline.fetch_gov
"""
from __future__ import annotations

import os
import sys
import time

import requests
from dotenv import load_dotenv

from pipeline.briefing_parse import split_sections, strip_html
from pipeline.config import INTERIM_DIR, MOFA_BRIEFING_ID
from pipeline.stage import fail, make_stage_meta, write_jsonl

API = "https://apis.data.go.kr/1262000/BriefingService/getBriefingList"
START = "2024-05-30"   # 제22대 개원


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv()
    key = os.environ.get("DATA_GO_KR")
    if not key:
        fail(".env 에 DATA_GO_KR 키가 없다 — 공공데이터포털 15141796 활용신청 필요")

    session = requests.Session()
    session.headers.update({"User-Agent": "agenda-entry-timeline/1.0"})
    rows: list[dict] = []
    page = 1
    while True:
        resp = session.get(API, params={
            "serviceKey": key, "returnType": "JSON",
            "pageNo": page, "numOfRows": 100}, timeout=60)
        resp.raise_for_status()
        payload = resp.json()
        items = payload.get("response", {}).get("body", {}).get("items", [])
        if not items:
            break
        for it in items:
            date = str(it.get("written_date") or it.get("writtenDate") or "")[:10]
            if date < START:
                continue
            sections = split_sections(strip_html(it.get("content", "")))
            rows.append({
                "briefing_id": str(it.get("seq") or it.get("id") or ""),
                "date": date,
                "url": it.get("url") or f"https://www.mofa.go.kr/www/brd/m_4078/view.do?seq={it.get('seq')}",
                "title": it.get("title", ""),
                **sections,
            })
        if len(items) < 100:
            break
        page += 1
        time.sleep(0.3)

    if not rows:
        fail("브리핑이 0건이다 — API 응답 구조나 키를 확인하라")
    rows.sort(key=lambda r: r["date"])
    with_qa = sum(1 for r in rows if r["qa"])
    print(f"  브리핑 {len(rows)}건  {rows[0]['date']} ~ {rows[-1]['date']}  질의응답 있는 건 {with_qa}")

    out = INTERIM_DIR / "briefings.jsonl"
    write_jsonl(out, rows, make_stage_meta("fetch_gov", [], len(rows)))
    print(f"[OK] {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
.venv/Scripts/python -m pytest tests/test_briefing_parse.py -v
```

Expected: 6 passed

- [ ] **Step 5: 응답 구조 확인 후 필드 매핑 확정**

`fetch_gov.py`의 `API` 경로와 필드명(`written_date`·`content`·`seq`)은 **미검증이다.**
키가 없어 실호출로 확인하지 못했다. 아래를 먼저 돌려 실제 구조를 눈으로 보고 맞춘다.

```bash
.venv/Scripts/python -c "
import os,json,requests
from dotenv import load_dotenv; load_dotenv()
r=requests.get('https://apis.data.go.kr/1262000/BriefingService/getBriefingList',
  params={'serviceKey':os.environ['DATA_GO_KR'],'returnType':'JSON','pageNo':1,'numOfRows':1},timeout=60)
print(r.status_code); print(r.text[:1500])
"
```

`404`나 `SERVICE_KEY_IS_NOT_REGISTERED_ERROR`가 나오면 https://www.data.go.kr/data/15141796/openapi.do
의 "요청주소"와 "출력값" 표를 열어 경로·필드명을 확인한다.
**`briefing_parse.py`는 고치지 않는다** — 이 스크립트의 매핑만 바꾼다.

- [ ] **Step 6: 실제 수집 실행**

```bash
.venv/Scripts/python -m pipeline.fetch_gov
```

Expected: 2024-05-30 이후 브리핑 200건 이상, 대부분 `qa` 비어 있지 않음

- [ ] **Step 7: 커밋**

```bash
git add pipeline/briefing_parse.py pipeline/fetch_gov.py tests/test_briefing_parse.py
git commit -m "feat: 외교부 브리핑 수집과 모두발언/질의응답 분리

정부가 먼저 꺼낸 것과 기자가 물어서 답한 것을 구분한다(스펙 7-4)."
```

---

## Task 9: 회기·일정·결측 구간 산출

**Files:**
- Create: `pipeline/calendar_calc.py`
- Create: `pipeline/calendar.py`
- Test: `tests/test_calendar_calc.py`

**Interfaces:**
- Consumes: `data/interim/meetings.jsonl`, `ENDPOINTS["session"]`, `ENDPOINTS["schedule"]`
- Produces:
  - `session_spans(rows: list[dict]) -> list[dict]` — `BILLSESSPROD` 응답 → `{"kind":"session","start","end","label"}`
  - `committee_days(rows: list[dict], committee: str) -> list[str]` — `ALLSCHEDULE` 응답 → 개회일(`YYYY-MM-DD`) 정렬 목록
  - `missing_minutes(scheduled: list[str], published: list[str]) -> list[dict]` — 차집합을 `{"kind":"minutes_missing","start","end","label"}` 구간으로
  - 실행 산출물: `data/interim/sessions.json`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_calendar_calc.py`:

```python
from pipeline.calendar_calc import committee_days, missing_minutes, session_spans

SESSIONS = [
    {"ERACO": "제22대", "SESS": "제418회", "SESS_BG_DT": "2024-09-02", "SESS_ED_DT": "2024-12-10"},
    {"ERACO": "제21대", "SESS": "제400회", "SESS_BG_DT": "2022-09-01", "SESS_ED_DT": "2022-12-09"},
]

SCHEDULE = [
    {"SCH_DT": "2026-05-20", "CMIT_NM": "외교통일위원회", "CONF_DIV": "전체회의"},
    {"SCH_DT": "2026-08-11", "CMIT_NM": "외교통일위원회", "CONF_DIV": "전체회의"},
    {"SCH_DT": "2026-08-11", "CMIT_NM": "국방위원회", "CONF_DIV": "전체회의"},
    {"SCH_DT": "2026-04-09", "CMIT_NM": "외교통일위원회", "CONF_DIV": "법안심사 소위원회"},
]


def test_session_spans_filter_by_era():
    got = session_spans(SESSIONS, eraco="제22대")
    assert len(got) == 1
    assert got[0] == {"kind": "session", "start": "2024-09-02",
                      "end": "2024-12-10", "label": "제418회"}


def test_committee_days_filters_and_sorts():
    assert committee_days(SCHEDULE, "외교통일") == ["2026-04-09", "2026-05-20", "2026-08-11"]


def test_committee_days_dedups():
    dup = SCHEDULE + [{"SCH_DT": "2026-05-20", "CMIT_NM": "외교통일위원회", "CONF_DIV": "전체회의"}]
    assert committee_days(dup, "외교통일").count("2026-05-20") == 1


def test_missing_minutes_finds_scheduled_without_published():
    got = missing_minutes(["2026-05-20", "2026-08-11"], ["2026-05-20"])
    assert got == [{"kind": "minutes_missing", "start": "2026-08-11",
                    "end": "2026-08-11", "label": "회의록 미발간"}]


def test_missing_minutes_merges_adjacent_days_into_one_span():
    got = missing_minutes(["2026-08-11", "2026-08-12"], [])
    assert len(got) == 1
    assert got[0]["start"] == "2026-08-11" and got[0]["end"] == "2026-08-12"


def test_missing_minutes_empty_when_all_published():
    assert missing_minutes(["2026-05-20"], ["2026-05-20"]) == []
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
.venv/Scripts/python -m pytest tests/test_calendar_calc.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.calendar_calc'`

- [ ] **Step 3: 최소 구현**

`pipeline/calendar_calc.py`:

```python
"""회기·개회일·결측 구간 산출.

회기 구간만으로는 부족하다(스펙 5-4). 배경 음영의 실질 기준은
위원회 실제 개회일이고, 결측은 일정 ∖ 회의록 차집합으로 잡는다.
"""
from __future__ import annotations

from datetime import date, timedelta


def session_spans(rows: list[dict], eraco: str) -> list[dict]:
    out = []
    for r in rows:
        if r.get("ERACO") != eraco:
            continue
        start, end = r.get("SESS_BG_DT"), r.get("SESS_ED_DT")
        if not start or not end:
            continue
        out.append({"kind": "session", "start": start, "end": end,
                    "label": r.get("SESS", "")})
    return sorted(out, key=lambda x: x["start"])


def committee_days(rows: list[dict], committee: str) -> list[str]:
    days = {r["SCH_DT"] for r in rows
            if committee in str(r.get("CMIT_NM", "")) and r.get("SCH_DT")}
    return sorted(days)


def _merge_runs(days: list[str], label: str, kind: str) -> list[dict]:
    spans: list[dict] = []
    for d in sorted(days):
        cur = date.fromisoformat(d)
        if spans and date.fromisoformat(spans[-1]["end"]) + timedelta(days=1) == cur:
            spans[-1]["end"] = d
        else:
            spans.append({"kind": kind, "start": d, "end": d, "label": label})
    return spans


def missing_minutes(scheduled: list[str], published: list[str]) -> list[dict]:
    gap = sorted(set(scheduled) - set(published))
    return _merge_runs(gap, "회의록 미발간", "minutes_missing")
```

`pipeline/calendar.py`:

```python
"""회기·일정 수집과 결측 구간 산출."""
from __future__ import annotations

import json
import os
import sys

from dotenv import load_dotenv

from pipeline.assembly_api import fetch_all
from pipeline.calendar_calc import committee_days, missing_minutes, session_spans
from pipeline.config import ENDPOINTS, ERACO_22, INTERIM_DIR, WTW_NAME
from pipeline.stage import fail, read_jsonl

YEARS = ["2024", "2025", "2026"]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv()
    key = os.environ.get("OPEN_ASSEMBLY")
    if not key:
        fail(".env 에 OPEN_ASSEMBLY 키가 없다")

    sess_rows = fetch_all(ENDPOINTS["session"], {}, key)
    sched_rows: list[dict] = []
    for year in YEARS:
        sched_rows.extend(fetch_all(ENDPOINTS["schedule"], {"SCH_DT": year}, key))

    _, meetings = read_jsonl(INTERIM_DIR / "meetings.jsonl")
    published = sorted({m["date"] for m in meetings if m.get("date")})
    scheduled = committee_days(sched_rows, WTW_NAME)

    spans = session_spans(sess_rows, eraco=ERACO_22)
    opens = [{"kind": "committee_open", "start": d, "end": d, "label": "외통위 개회"}
             for d in scheduled]
    missing = missing_minutes(scheduled, published)

    print(f"  회기 {len(spans)}구간 / 외통위 일정 {len(scheduled)}일 / 회의록 {len(published)}일")
    print(f"  회의록 미발간 구간 {len(missing)}개")
    for m in missing:
        print(f"    {m['start']} ~ {m['end']}")
    if not scheduled:
        fail("외통위 일정이 0건이다 — CMIT_NM 필터를 확인하라")

    out = INTERIM_DIR / "sessions.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spans + opens + missing, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"[OK] {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
.venv/Scripts/python -m pytest tests/test_calendar_calc.py -v
```

Expected: 6 passed

- [ ] **Step 5: 실제 실행 — 발간 시차 확인**

```bash
.venv/Scripts/python -m pipeline.calendar
```

Expected: `회의록 미발간 구간`에 **2026-08-11**이 포함된다. 스펙 5-4(a)의 실측과 일치해야 한다. 안 나오면 필터나 날짜 형식을 의심한다.

- [ ] **Step 6: 커밋**

```bash
git add pipeline/calendar_calc.py pipeline/calendar.py tests/test_calendar_calc.py
git commit -m "feat: 회기·개회일·회의록 결측 구간 산출

일정 ∖ 회의록 차집합으로 발간 시차를 검출한다."
```

---

## Task 10: 임베딩과 오케스트레이션

**Files:**
- Create: `pipeline/embed.py`
- Create: `pipeline/run.py`
- Test: `tests/test_embed.py`

**Interfaces:**
- Consumes: `data/interim/turns.jsonl`, `data/interim/briefings.jsonl`, `OPENAI_API_KEY`
- Produces:
  - `build_texts(turns: list[dict], briefings: list[dict]) -> list[dict]` — `{"doc_id","axis","date","text"}`
  - `save_matrix(path: Path, vectors: list[list[float]]) -> None` — float32 `.npy`
  - 실행 산출물: `data/embeddings.npy`, `data/interim/embed_index.jsonl`
  - `pipeline/run.py` — `python -m pipeline.run --from fetch_nk`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_embed.py`:

```python
import numpy as np

from pipeline.embed import build_texts, save_matrix

TURNS = [
    {"conf_id": "1", "date": "2024-07-17", "turn_index": 1, "speaker": "홍길동",
     "role": "위원", "text": "발언 내용입니다."},
    {"conf_id": "1", "date": "2024-07-17", "turn_index": 2, "speaker": None,
     "role": None, "text": "   "},
]
BRIEFINGS = [
    {"briefing_id": "9", "date": "2024-08-01", "opening": "모두 발언입니다.",
     "qa": [{"question": "질문", "answer": "답변", "asker": "OO일보"}]},
]


def test_turn_docs_have_axis_and_stable_id():
    docs = build_texts(TURNS, [])
    assert docs[0]["doc_id"] == "nk:1:1"
    assert docs[0]["axis"] == "nk"


def test_blank_turns_are_dropped():
    assert len(build_texts(TURNS, [])) == 1


def test_briefing_opening_and_qa_become_separate_docs():
    docs = build_texts([], BRIEFINGS)
    ids = [d["doc_id"] for d in docs]
    assert ids == ["gov:9:opening", "gov:9:qa:0"]


def test_qa_doc_text_contains_both_question_and_answer():
    docs = build_texts([], BRIEFINGS)
    assert "질문" in docs[1]["text"] and "답변" in docs[1]["text"]


def test_save_matrix_is_float32(tmp_path):
    path = tmp_path / "e.npy"
    save_matrix(path, [[0.1, 0.2], [0.3, 0.4]])
    arr = np.load(path)
    assert arr.dtype == np.float32
    assert arr.shape == (2, 2)
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
.venv/Scripts/python -m pytest tests/test_embed.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.embed'`

- [ ] **Step 3: 최소 구현**

`pipeline/embed.py`:

```python
"""임베딩 생성. 정확 검색용이라 인덱스를 만들지 않는다(스펙 10-1).

임베딩은 필수 경로가 아니라 키워드·안건명이 놓친 것을 잡는 보강 경로다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

from pipeline.config import DATA_DIR, INTERIM_DIR
from pipeline.stage import fail, make_stage_meta, read_jsonl, write_jsonl

MODEL = "text-embedding-3-small"
BATCH = 256


def build_texts(turns: list[dict], briefings: list[dict]) -> list[dict]:
    docs: list[dict] = []
    for t in turns:
        text = (t.get("text") or "").strip()
        if not text:
            continue
        docs.append({
            "doc_id": f"nk:{t['conf_id']}:{t['turn_index']}",
            "axis": "nk", "date": t["date"], "text": text,
        })
    for b in briefings:
        opening = (b.get("opening") or "").strip()
        if opening:
            docs.append({"doc_id": f"gov:{b['briefing_id']}:opening",
                         "axis": "gov", "date": b["date"], "text": opening})
        for i, qa in enumerate(b.get("qa") or []):
            text = f"{qa.get('question','')}\n{qa.get('answer','')}".strip()
            if text:
                docs.append({"doc_id": f"gov:{b['briefing_id']}:qa:{i}",
                             "axis": "gov", "date": b["date"], "text": text})
    return docs


def save_matrix(path: Path, vectors: list[list[float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, np.asarray(vectors, dtype=np.float32))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv()
    if not os.environ.get("OPENAI_API_KEY"):
        fail(".env 에 OPENAI_API_KEY 가 없다")
    from openai import OpenAI

    _, turns = read_jsonl(INTERIM_DIR / "turns.jsonl")
    _, briefings = read_jsonl(INTERIM_DIR / "briefings.jsonl")
    docs = build_texts(turns, briefings)
    print(f"  임베딩 대상 {len(docs)}건")

    client = OpenAI()
    vectors: list[list[float]] = []
    for i in range(0, len(docs), BATCH):
        chunk = docs[i:i + BATCH]
        resp = client.embeddings.create(model=MODEL, input=[d["text"][:8000] for d in chunk])
        vectors.extend(item.embedding for item in resp.data)
        print(f"    {min(i + BATCH, len(docs))}/{len(docs)}")

    if len(vectors) != len(docs):
        fail(f"임베딩 수 불일치 docs={len(docs)} vectors={len(vectors)}")

    save_matrix(DATA_DIR / "embeddings.npy", vectors)
    index = [{k: d[k] for k in ("doc_id", "axis", "date")} for d in docs]
    write_jsonl(INTERIM_DIR / "embed_index.jsonl", index,
                make_stage_meta("embed", [INTERIM_DIR / "turns.jsonl"], len(index)))
    print(f"[OK] data/embeddings.npy  shape=({len(vectors)}, {len(vectors[0])})")


if __name__ == "__main__":
    main()
```

`pipeline/run.py`:

```python
"""단계 오케스트레이션.

  python -m pipeline.run                # 전체
  python -m pipeline.run --from parse   # parse 부터
"""
from __future__ import annotations

import argparse
import subprocess
import sys

STAGES = ["fetch_nk", "download_pdf", "extract", "parse", "fetch_gov", "calendar", "embed"]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", choices=STAGES, default=STAGES[0])
    args = ap.parse_args()
    begin = STAGES.index(args.start)
    for stage in STAGES[begin:]:
        print(f"\n=== {stage} ===")
        code = subprocess.call([sys.executable, "-m", f"pipeline.{stage}"])
        if code != 0:
            print(f"[STOP] {stage} 실패 (exit {code}) — 다음 단계로 넘어가지 않는다", file=sys.stderr)
            sys.exit(code)
    print("\n[OK] 전체 파이프라인 완료")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
.venv/Scripts/python -m pytest tests/test_embed.py -v
```

Expected: 5 passed

- [ ] **Step 5: 전체 파이프라인 실행**

```bash
.venv/Scripts/python -m pipeline.run
```

Expected: 7단계 전부 통과 후 `[OK] 전체 파이프라인 완료`

- [ ] **Step 6: 전체 테스트 실행**

```bash
.venv/Scripts/python -m pytest -v
```

Expected: 전 테스트 통과 (약 46개). 네트워크·API 키 없이 돌아야 한다.

- [ ] **Step 7: 커밋**

```bash
git add pipeline/embed.py pipeline/run.py tests/test_embed.py
git commit -m "feat: 임베딩 생성과 파이프라인 오케스트레이션

게이트 실패 시 다음 단계로 넘어가지 않는다."
```

---

## 완료 기준 (계획 1)

- [ ] `data/interim/meetings.jsonl` — **87건** (상임위 54 + 국정감사 31 + 인사청문회 2)
- [ ] 모든 회의에 `pdf_url`이 있다 (없으면 정규화가 예외를 던진다)
- [ ] `data/interim/pages.jsonl` — 빈 페이지 0
- [ ] `data/interim/turns.jsonl` — 화자 미상 비율 5% 이하
- [ ] `data/interim/briefings.jsonl` — 2024-05-30 이후, `qa` 분리됨
- [ ] `data/interim/sessions.json` — 회기·개회일·**회의록 미발간 구간(2026-08-11 포함)**
- [ ] `data/embeddings.npy` — 행수가 `embed_index.jsonl`과 일치
- [ ] `fixtures/timeline.sample.json`이 스키마를 통과
- [ ] `pytest` 전체 통과 (네트워크·키 없이)
- [ ] `python -m pipeline.run`이 처음부터 끝까지 exit 0

---

## 이어지는 계획

**계획 2 — 탐지와 검증** (`scan.py`, `metrics.py`, `rubric.md`, `decisions.jsonl`)
이슈 8개 확정 → 키워드 사전 → 시간순 정방향 스캔(M=8) → LLM 캐시 → 사람 전수 검증 →
정밀도·재현율. 계획 1의 `turns.jsonl` / `briefings.jsonl` / `embeddings.npy`를 입력으로 쓴다.

**계획 3 — 화면과 배포** (`web/`, `build.py`)
가지 타임라인 · 맥락띠 · 증거 패널 · x축 토글 · GitHub Pages.
`schema/timeline.schema.json`과 `fixtures/timeline.sample.json`만 있으면 계획 1·2와
**병렬로 시작할 수 있다**(스펙 10-5 계약 우선).

---

## 선행 조건 — 지금 사람이 해야 할 일

**계획 1의 Task 8을 시작하기 전에** 공공데이터포털에서 활용신청이 필요하다
(자동승인·무료·즉시):

- 외교부_브리핑 `15141796` — https://www.data.go.kr/data/15141796/openapi.do
- 외교부_보도자료 `15141564` (보조) — https://www.data.go.kr/data/15141564/openapi.do

발급 키를 `.env`에 `DATA_GO_KR=` 로 넣는다. Task 1~7은 이것 없이 진행할 수 있다.
