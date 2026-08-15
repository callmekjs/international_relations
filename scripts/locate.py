"""
[2] locate — 연도별로 「외교정책 기조」 절이 어디 있는지 후보를 모은다.

**판정하지 않는다.** 스펙 §6 에 적힌 대로 규칙 기반 추출은 절반도 못 잡는다.
항목 표기가 정부마다 다르기 때문이다(첫째·둘째 / 1.2.3. / 글머리 기호 /
문장 속 나열 / 산문). 그래서 여기서는 사람이 볼 자리를 좁혀줄 뿐이고,
무엇이 항목인지는 사람이 원문을 보고 정한다.

출력: reports/기조절_후보.md

실행:
    python scripts/locate.py
    python scripts/locate.py 2013 2018
"""

LOCATOR_VERSION = "v1.0"

import io
import json
import re
import sys
from pathlib import Path

from stage_io import PROJECT_ROOT, REPORTS_ROOT, write_text_atomic

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

TEXT_ROOT = PROJECT_ROOT / "text"

# 추출본은 연도에 따라 공백이 통째로 사라지기도 한다(2003년 공백률 8%).
# 그래서 글자 사이에 공백이 있든 없든 잡히도록 짠다.
def _loose(term: str) -> re.Pattern:
    return re.compile(r"\s*".join(map(re.escape, term)))


HEADINGS = [
    ("외교정책 기조", _loose("외교정책기조")),
    ("정책 기조", _loose("정책기조")),
    ("외교 기조", _loose("외교기조")),
]

CONTEXT_BEFORE, CONTEXT_AFTER = 120, 900


def load_pages(year: int) -> list[dict]:
    p = TEXT_ROOT / f"{year}.pages.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("sources", [])


def locate_page(sources: list[dict], pos: int) -> str:
    """글자 위치를 '파일 · 쪽' 표기로 바꾼다."""
    for s in sources:
        for pg in s["pages"]:
            if pg["start"] <= pos < pg["end"]:
                half = f"·{pg['half']}" if pg.get("half") else ""
                return f"{s['file']} {pg['page']}쪽{half}"
    return "(위치 불명)"


def find_candidates(text: str) -> list[tuple[str, int]]:
    hits: list[tuple[str, int]] = []
    seen: set[int] = set()
    for label, pat in HEADINGS:
        for m in pat.finditer(text):
            # 같은 자리를 여러 패턴이 겹쳐 잡으면 한 번만
            if any(abs(m.start() - s) < 40 for s in seen):
                continue
            seen.add(m.start())
            hits.append((label, m.start()))
    hits.sort(key=lambda t: t[1])
    return hits


def main() -> None:
    years = [int(a) for a in sys.argv[1:] if a.isdigit()]
    files = sorted(TEXT_ROOT.glob("*.txt"), key=lambda p: p.stem)
    if years:
        files = [f for f in files if int(f.stem) in years]

    lines = [
        "# 「외교정책 기조」 절 후보",
        "",
        f"locate {LOCATOR_VERSION} 가 모은 자리다. **판정은 사람이 한다.**",
        "표기 방식이 정부마다 달라 규칙으로는 절반도 못 잡는다(스펙 §6).",
        "",
        "각 연도에서 진짜 기조 절을 고른 뒤 `authoring/editions.tsv` 에 위치와",
        "표기 방식(markStyle)을 적는다. 그 기록 자체가 자료가 된다 —",
        "'정부가 자기 항목에 이름 붙이는 방식'의 연대기이기 때문이다.",
        "",
    ]
    summary = []

    for f in files:
        year = int(f.stem)
        text = f.read_text(encoding="utf-8")
        sources = load_pages(year)
        ocr = any(s.get("ocr") for s in sources)
        hits = find_candidates(text)
        summary.append((year, len(hits), ocr))

        lines.append(f"\n---\n\n## {year}년" + ("  ⚠ OCR 유래 — 오탈자 가능" if ocr else ""))
        if not hits:
            lines.append("\n**후보 없음.** 표기가 달라 못 잡았을 수 있으니 원문을 직접 봐야 한다.\n")
            continue
        lines.append(f"\n후보 {len(hits)}곳\n")
        for label, pos in hits:
            where = locate_page(sources, pos)
            snippet = text[max(0, pos - CONTEXT_BEFORE): pos + CONTEXT_AFTER]
            snippet = re.sub(r"\n{2,}", "\n", snippet).strip()
            lines.append(f"\n### `{label}` — {where}  (글자 {pos:,})\n")
            lines.append("```")
            lines.append(snippet)
            lines.append("```")

    out = REPORTS_ROOT / "기조절_후보.md"
    write_text_atomic(out, "\n".join(lines) + "\n")

    print(f"locate {LOCATOR_VERSION} — {len(files)}개년\n")
    print(f"{'연도':<6}{'후보':>5}  비고")
    print("-" * 34)
    none_years = []
    for year, n, ocr in summary:
        note = "OCR" if ocr else ""
        if n == 0:
            note = (note + " 후보없음").strip()
            none_years.append(year)
        print(f"{year:<6}{n:>5}  {note}")

    print(f"\n리포트: {out}")
    if none_years:
        print(f"후보를 못 찾은 해: {', '.join(map(str, none_years))} — 원문 확인 필요")


if __name__ == "__main__":
    main()
