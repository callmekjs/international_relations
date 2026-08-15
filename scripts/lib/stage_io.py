"""파이프라인 공용 I/O — 원자적 쓰기 + 실패 목록 기록.

National_Assembly_3 의 같은 이름 모듈에서 가져온 습관이다. 규모는 다르지만
이유는 그대로다.

  - 결과 파일을 최종 경로에 직접 쓰면 중단(Ctrl-C·크래시) 시 반쪽 파일이 남고,
    "파일 존재 = 완료" 스킵과 결합해 영원히 재처리되지 않는다 → tmp + os.replace
  - 실패가 화면 출력으로만 스치고 exit 0 으로 삼켜지면 어디에도 남지 않는다
    → 실패 목록 파일 + non-zero exit
"""

import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent   # scripts/lib/ → 프로젝트 뿌리
REPORTS_ROOT = PROJECT_ROOT / "reports"
FAILURES_ROOT = REPORTS_ROOT / "failures"


def write_text_atomic(out_path: Path, text: str) -> int:
    """텍스트를 임시 파일에 전부 쓴 뒤 os.replace 로 최종 경로에 놓는다.
    중단되면 최종 파일이 아예 안 생겨 다음 실행에서 자연히 재처리된다.
    반환: 쓴 글자 수."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, out_path)
    finally:
        tmp.unlink(missing_ok=True)  # 실패 시 잔해 제거 (성공 시엔 이미 이동돼 없음)
    return len(text)


def write_json_atomic(out_path: Path, obj) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, out_path)
    finally:
        tmp.unlink(missing_ok=True)


def report_failures(stage: str, failures: list[tuple[str, str]]) -> Path | None:
    """(대상, 사유) 목록을 reports/failures/{stage}_failures.txt 에 기록.
    실패 0건이면 이전 실행의 스테일 파일을 지운다. 반환: 기록 시 파일 경로."""
    path = FAILURES_ROOT / f"{stage}_failures.txt"
    if not failures:
        path.unlink(missing_ok=True)
        return None
    FAILURES_ROOT.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {stage} 실패 {len(failures)}건 — 원인 해결 후 재실행하면 실패분만 다시 처리된다\n")
        for target, reason in failures:
            f.write(f"{target}\t{reason}\n")
    return path
