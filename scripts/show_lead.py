"""기조 절 첫머리만 압축해 보여준다 — authoring 초안을 쓸 때 쓰는 보기 도구.

항목 목록은 거의 언제나 절 첫 문단에 있다(리드 문장에 나열하거나 번호를 붙여
늘어놓는다). 그래서 절 전체가 아니라 앞부분만 보면 된다.

실행:
    python scripts/show_lead.py 1998 1999 2000
    python scripts/show_lead.py --chars 3000 2013
"""

import io
import re
import sys
from pathlib import Path

from stage_io import REPORTS_ROOT

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SECTIONS = REPORTS_ROOT / "sections"


def squeeze(s: str) -> str:
    """쪽 번호·머리글 때문에 생긴 빈 줄을 걷어 읽기 쉽게."""
    s = re.sub(r"\n[ \t]*\n+", "\n", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip()


def main() -> None:
    args = sys.argv[1:]
    chars = 2200
    if "--chars" in args:
        i = args.index("--chars")
        chars = int(args[i + 1])
        del args[i:i + 2]
    years = [int(a) for a in args if a.isdigit()]

    for year in years:
        p = SECTIONS / f"{year}.md"
        print(f"\n{'=' * 78}\n{year}\n{'=' * 78}")
        if not p.exists():
            print("(섹션 파일 없음)")
            continue
        body = p.read_text(encoding="utf-8")
        m = re.search(r"```\n(.*?)\n```", body, re.S)
        if not m:
            print("(구간 없음)")
            continue
        print(squeeze(m.group(1))[:chars])


if __name__ == "__main__":
    main()
