"""
[2b] dump_sections — 연도별 「외교정책 기조」 절 원문을 따로 떠낸다.

locate 가 찾은 후보 중 목차 줄이 아니라 실제 본문인 자리를 골라
reports/sections/<연도>.md 로 떼어 놓는다. authoring 초안을 쓸 때 이 파일만
보면 되도록 하는 것이 목적이다.

고르는 방식은 어림이다. 최종 판단은 사람이 원문을 보고 한다(스펙 §6).

실행:
    python scripts/dump_sections.py
    python scripts/dump_sections.py 2013 2018
"""

import io
import json
import re
import sys
from pathlib import Path

from locate import HEADINGS, load_pages, locate_page
from stage_io import PROJECT_ROOT, REPORTS_ROOT, write_text_atomic

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

TEXT_ROOT = PROJECT_ROOT / "text"
OUT_ROOT = REPORTS_ROOT / "sections"

SECTION_CHARS = 5000   # 기조 절은 길어야 서너 쪽이다
LEAD_CHARS = 60

# 절 표시가 앞에 붙은 자리만 고른다. 백서는 쪽마다 '2013년 국제 정세 및 /
# 외교정책 기조' 라는 머리글을 반복해 넣어서, 제목만 보고 고르면 그 머리글에
# 걸린다. '제N절' 뒤에 (연도) 외교정책 기조 가 오는 형태라야 진짜 절 시작이다.
_SECTION_MARK = re.compile(
    r"제\s*\d{1,2}\s*절"            # 제 2 절
    r"\s*"
    r"(?:\d{4}\s*년\s*도?\s*)?"     # 1998년도  (옛 판은 절 제목에 연도가 붙는다)
    r"\s*"
    + r"\s*".join("외교정책기조")     # 공백이 사라진 추출본(2003년)도 잡히게
)


def prose_score(s: str) -> int:
    """목차 줄과 본문을 가르는 어림값.
    목차는 '제3절 …  37' 처럼 숫자로 끝나는 짧은 줄이 이어지고,
    본문은 '…하였다.' 로 끝나는 긴 문장이 이어진다."""
    return len(re.findall(r"(하였다|되었다|이다|한다|였다)[.\s]", s))


def pick(text: str) -> list[int]:
    """절 표시가 붙은 자리를 우선하고, 없으면 제목만이라도 고른다."""
    marked = [m.start() for m in _SECTION_MARK.finditer(text)]
    if marked:
        # 같은 절이 목차에도 한 번 나오므로 본문다운 쪽을 앞에 둔다
        marked.sort(key=lambda p: -prose_score(text[p: p + 2500]))
        out: list[int] = []
        for p in marked:
            if not any(abs(p - s) < 500 for s in out):
                out.append(p)
        return out[:2]

    cands: list[tuple[int, int]] = []
    seen: list[int] = []
    for _, pat in HEADINGS:
        for m in pat.finditer(text):
            if any(abs(m.start() - s) < 200 for s in seen):
                continue
            seen.append(m.start())
            cands.append((prose_score(text[m.start(): m.start() + 2500]), m.start()))
    cands.sort(reverse=True)
    return [pos for score, pos in cands[:2] if score > 0] or [p for _, p in cands[:1]]


def main() -> None:
    want = {int(a) for a in sys.argv[1:] if a.isdigit()}
    files = sorted(TEXT_ROOT.glob("*.txt"), key=lambda p: p.stem)
    if want:
        files = [f for f in files if int(f.stem) in want]

    print(f"{'연도':<6}{'구간':>4}{'글자':>8}  출처")
    print("-" * 60)
    for f in files:
        year = int(f.stem)
        text = f.read_text(encoding="utf-8")
        sources = load_pages(year)
        ocr = any(s.get("ocr") for s in sources)
        positions = pick(text)

        lines = [f"# {year}년 「외교정책 기조」 절 원문", ""]
        if ocr:
            lines += ["> ⚠ 이 해는 OCR 로 읽었다. 오탈자가 있을 수 있으므로",
                      "> 인용을 옮길 때 원본 PDF 를 함께 봐야 한다.", ""]
        if not positions:
            lines += ["**후보를 찾지 못했다.** 원본을 직접 봐야 한다.", ""]

        for n, pos in enumerate(positions, 1):
            start = max(0, pos - LEAD_CHARS)
            seg = text[start: pos + SECTION_CHARS]
            seg = re.sub(r"\n{3,}", "\n\n", seg)
            lines += [f"## 구간 {n} — {locate_page(sources, pos)} (글자 {pos:,})", "",
                      "```", seg.strip(), "```", ""]

        out = OUT_ROOT / f"{year}.md"
        write_text_atomic(out, "\n".join(lines) + "\n")
        note = "OCR" if ocr else ""
        print(f"{year:<6}{len(positions):>4}{len(text):>8,}  {note}")

    print(f"\n출력: {OUT_ROOT}")


if __name__ == "__main__":
    main()
