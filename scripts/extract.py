"""
[1] extract — 원본 문서를 대상연도별 텍스트로 뽑는다.

    data/<대상연도>/*.{pdf,hwp,doc}  →  text/<대상연도>.txt
                                        text/<대상연도>.pages.json

「외교정책 기조」 절은 제1장(2002년 이후) 또는 제2장(2001년 이전)에만 있다.
그래서 백서 전문(약 12,000면)을 다루지 않고 앞부분 장과 발간사만 읽는다.

실행:
    python scripts/extract.py                 # 1998~2025 전체
    python scripts/extract.py 2013 2018       # 특정 연도만
    python scripts/extract.py --from 2003 --to 2016
    python scripts/extract.py --force         # 이미 만든 것도 다시
"""

EXTRACTOR_VERSION = "v1.5"   # v1.1 머리글 제거 / v1.4 인쇄된 쪽번호 기록

import hashlib
import io
import re
import sys
from pathlib import Path

from dehead import strip_pages
from formats import read_any
from stage_io import PROJECT_ROOT, REPORTS_ROOT, report_failures, write_json_atomic, write_text_atomic

if __name__ == "__main__":  # import 시(테스트 등) 부작용 방지
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DATA_ROOT = PROJECT_ROOT / "data"
TEXT_ROOT = PROJECT_ROOT / "text"

# 이 프로젝트의 범위.
#
# 예전에는 1998 부터였다 — "1989~1997 은 전부 스캔본이라 OCR 공정이 따로
# 필요해 제외한다" 는 것이 이유였다. **그 OCR 공정이 생겼으므로 이유가
# 사라졌다**(2026-08-16). 그대로 두면 화면이 노태우·김영삼 두 정권,
# 아홉 해를 통째로 못 보여준다 — 정권 교체 비교도 8건 중 6건만 나온다.
SCOPE_FROM, SCOPE_TO = 1989, 2025

# 기조 절이 들어 있을 수 있는 장. 앞의 두 장이면 모든 세대를 덮는다.
CHAPTERS_WANTED = (1, 2)

# 파일명 → 역할. 연도별 예외표를 두지 않고 이름 생김새만으로 가른다.
_RE_APPENDIX = re.compile(r"부록")
_RE_FRONT = re.compile(r"발간사|머리말|목차|표지|인사말")
_RE_CHAPTER_PATTERNS = (
    re.compile(r"제\s*(\d{1,2})\s*장"),        # 제1장, 제 1 장
    re.compile(r"[(\-_\s](\d{1,2})\s*장"),     # -1장, (1장), _1장, ' 1장'
    re.compile(r"\s(\d{2})$"),                 # '2012 외교백서 01'
)


def classify(stem: str) -> tuple[str, int | None]:
    """(역할, 장번호) 반환. 역할: appendix | front | chapter | whole"""
    if _RE_APPENDIX.search(stem):
        return "appendix", None
    for pat in _RE_CHAPTER_PATTERNS:
        m = pat.search(stem)
        if m:
            return "chapter", int(m.group(1))
    if _RE_FRONT.search(stem):
        return "front", None
    return "whole", None


def wanted(role: str, chapter: int | None) -> bool:
    if role == "appendix":
        return False
    if role == "chapter":
        return chapter in CHAPTERS_WANTED
    return True  # front, whole


def sort_key(role: str, chapter: int | None) -> tuple[int, int]:
    order = {"front": 0, "chapter": 1, "whole": 2}
    return (order.get(role, 9), chapter or 0)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def discover_years() -> list[int]:
    years = []
    for d in DATA_ROOT.iterdir():
        if d.is_dir() and d.name.isdigit():
            years.append(int(d.name))
    return sorted(years)


def select_files(year: int) -> list[tuple[Path, str, int | None]]:
    """그 해 폴더에서 읽을 파일을 고른다. (경로, 역할, 장번호)"""
    folder = DATA_ROOT / str(year)
    picked = []
    for f in sorted(folder.iterdir()):
        if not f.is_file() or f.suffix.lower() not in (".pdf", ".hwp", ".doc"):
            continue
        role, chapter = classify(f.stem)
        if wanted(role, chapter):
            picked.append((f, role, chapter))
    picked.sort(key=lambda t: sort_key(t[1], t[2]))
    return picked


def process_year(year: int, force: bool) -> tuple[str, str]:
    """반환: (상태, 메시지). 상태: ok | skip | fail"""
    folder = DATA_ROOT / str(year)
    if not folder.exists():
        return "fail", "폴더 없음"

    picked = select_files(year)
    if not picked:
        return "fail", "읽을 파일 없음 (제1·2장·발간사 어느 것도 못 찾음)"

    txt_path = TEXT_ROOT / f"{year}.txt"
    meta_path = TEXT_ROOT / f"{year}.pages.json"

    # 멱등: 산출물이 있고 원본 지문이 그대로면 건너뛴다.
    # 폴더 존재만 보면 원본이 교체돼도 옛 결과가 영원히 쓰인다.
    if not force and txt_path.exists() and meta_path.exists():
        import json
        try:
            prev = json.loads(meta_path.read_text(encoding="utf-8"))
            prev_hashes = {s["file"]: s.get("sha256") for s in prev.get("sources", [])}
            if prev.get("extractorVersion") == EXTRACTOR_VERSION and \
               all(prev_hashes.get(f.name) == sha256(f) for f, _, _ in picked) and \
               len(prev_hashes) == len(picked):
                return "skip", f"이미 있음 ({len(picked)}개 파일)"
        except Exception:
            pass  # 메타가 깨졌으면 그냥 다시 만든다

    parts: list[str] = []
    sources: list[dict] = []
    cursor = 0
    failures: list[str] = []

    for path, role, chapter in picked:
        pages, err = read_any(path)
        if err:
            failures.append(f"{path.name}: {err}")
            sources.append({
                "file": path.name, "role": role, "chapter": chapter,
                "format": path.suffix.lower().lstrip("."), "sha256": sha256(path),
                "status": "failed", "error": err, "pages": [],
            })
            continue

        # 쪽마다 반복되는 머리글·꼬리글을 걷어낸다. 그대로 두면 그 조각이
        # 본문 문장 한가운데로 끼어들어 인용을 원문 그대로 쓸 수 없게 된다.
        pages, head_stats = strip_pages(pages)

        page_index = []
        for p in pages:
            text = p["text"]
            if not text.endswith("\n"):
                text += "\n"
            start = cursor
            parts.append(text)
            cursor += len(text)
            page_index.append({"page": p["page"], "half": p["half"],
                               "printedPage": p.get("printedPage"),
                               "start": start, "end": cursor})

        sources.append({
            "file": path.name, "role": role, "chapter": chapter,
            "format": path.suffix.lower().lstrip("."), "sha256": sha256(path),
            "status": "ok",
            "spread": any(p["half"] for p in pages),
            "ocr": any(p.get("ocr") for p in pages),  # 하류가 OCR 유래를 구별해야 한다
            "runningHeads": head_stats,
            "pages": page_index,
        })

    body = "".join(parts)
    ok_sources = [s for s in sources if s["status"] == "ok"]

    if not ok_sources:
        # 하나도 못 읽었으면 산출물을 만들지 않는다 — 빈 파일이 "내용 없는 해"로 오해된다
        return "fail", "; ".join(failures)

    write_text_atomic(txt_path, body)
    write_json_atomic(meta_path, {
        "year": year,
        "extractorVersion": EXTRACTOR_VERSION,
        "chars": len(body),
        "sources": sources,
    })

    msg = f"{len(ok_sources)}개 파일 / {len(body):,}자"
    if failures:
        msg += f" / 일부 실패 {len(failures)}건"
    return "ok", msg


def parse_args(argv: list[str]) -> tuple[list[int], bool]:
    force = "--force" in argv
    argv = [a for a in argv if a != "--force"]

    lo, hi = SCOPE_FROM, SCOPE_TO
    explicit: list[int] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--from":
            lo = int(argv[i + 1]); i += 2
        elif a == "--to":
            hi = int(argv[i + 1]); i += 2
        elif a.isdigit():
            explicit.append(int(a)); i += 1
        else:
            print(f"[ERROR] 알 수 없는 인자: {a}")
            sys.exit(2)

    available = discover_years()
    if explicit:
        years = [y for y in available if y in explicit]
        missing = sorted(set(explicit) - set(years))
        if missing:
            print(f"[주의] data/ 에 없는 연도: {', '.join(map(str, missing))}")
    else:
        years = [y for y in available if lo <= y <= hi]
    return years, force


def main() -> None:
    years, force = parse_args(sys.argv[1:])
    if not years:
        print("[ERROR] 처리할 연도가 없다.")
        sys.exit(1)

    print(f"extract {EXTRACTOR_VERSION} — {len(years)}개년 ({years[0]}~{years[-1]})")
    print(f"대상 장: 제{'·제'.join(map(str, CHAPTERS_WANTED))}장 + 발간사/목차\n")

    counts = {"ok": 0, "skip": 0, "fail": 0}
    failures: list[tuple[str, str]] = []
    for year in years:
        status, msg = process_year(year, force)
        counts[status] += 1
        mark = {"ok": "  OK  ", "skip": " skip ", "fail": " FAIL "}[status]
        print(f"[{mark}] {year}  {msg}")
        if status == "fail":
            failures.append((str(year), msg))

    print(f"\n완료 {counts['ok']} / 건너뜀 {counts['skip']} / 실패 {counts['fail']}")
    print(f"출력: {TEXT_ROOT}")

    write_json_atomic(REPORTS_ROOT / "extract_report.json", {
        "extractorVersion": EXTRACTOR_VERSION,
        "years": years,
        "counts": counts,
        "failures": [{"year": y, "reason": r} for y, r in failures],
    })

    fail_path = report_failures("extract", failures)
    if fail_path:
        print(f"실패 목록: {fail_path}")
        # 스캔본(2017·2019)은 알려진 미해결이라 여기서 빌드를 세우지는 않는다.
        # 하류(verify)가 해당 연도를 blocked 로 다루는지로 판단한다.


if __name__ == "__main__":
    main()
