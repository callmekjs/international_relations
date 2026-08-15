"""
[3d] fill_pages — 인용문이 실린 **인쇄 쪽수**를 자동으로 채운다.

연구자가 인용할 때 필요한 것은 PDF 의 몇 번째 장이 아니라 책에 찍힌 쪽수다.
extract 가 머리글을 지우면서 그 숫자를 기록해 두었으므로(pages.json 의
printedPage), 인용문이 원문 몇 번째 글자인지만 알면 되짚을 수 있다.

손으로 87개를 옮겨 적는 것보다 정확하다 — 사람은 쪽을 잘못 볼 수 있지만
이쪽은 인용문이 실제로 놓인 자리에서 읽는다.

**사람이 이미 적어 넣은 쪽수는 건드리지 않는다.** 사람이 인쇄본을 직접 보고
적은 것이 기계 추정보다 믿을 만하고, 둘이 다르면 그 사실 자체가 신호다.

실행
    python scripts/fill_pages.py --dry-run
    python scripts/fill_pages.py
"""

import io
import json
import re
import sys

from normalize import normalize_for_match
from stage_io import PROJECT_ROOT, write_text_atomic
from verify import read_tsv

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

TEXT_ROOT = PROJECT_ROOT / "text"
AUTHORING = PROJECT_ROOT / "authoring"
TARGET = AUTHORING / "priorities.tsv"


def locate(text: str, needle: str) -> int | None:
    """인용문이 원문에서 시작하는 글자 위치. 공백이 사라진 판본도 잡히게
    글자 사이를 열어둔 정규식으로 찾는다."""
    core = re.sub(r"\s+", "", needle)[:40]
    if len(core) < 8:
        return None
    pat = re.compile(r"\s*".join(map(re.escape, core)))
    m = pat.search(text)
    return m.start() if m else None


def page_at(sources: list[dict], pos: int) -> tuple[int | None, int | None, str | None]:
    """(인쇄쪽, PDF쪽, 파일명)"""
    for s in sources:
        for pg in s["pages"]:
            if pg["start"] <= pos < pg["end"]:
                return pg.get("printedPage"), pg.get("page"), s["file"]
    return None, None, None


def main() -> None:
    dry = "--dry-run" in sys.argv

    lines = TARGET.read_text(encoding="utf-8").splitlines()
    header: list[str] | None = None
    out: list[str] = []
    filled = missed = kept = 0

    cache: dict[int, tuple[str, list[dict]]] = {}

    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            out.append(line)
            continue
        cols = line.split("\t")
        if header is None:
            header = cols
            out.append(line)
            continue
        cols += [""] * (len(header) - len(cols))

        pi = header.index("srcPage")
        if cols[pi].strip():
            kept += 1
            out.append("\t".join(cols))
            continue

        y = int(cols[header.index("coverageYear")])
        if y not in cache:
            txt = (TEXT_ROOT / f"{y}.txt")
            meta = (TEXT_ROOT / f"{y}.pages.json")
            cache[y] = (txt.read_text(encoding="utf-8") if txt.exists() else "",
                        json.loads(meta.read_text(encoding="utf-8"))["sources"] if meta.exists() else [])
        text, sources = cache[y]

        pos = locate(text, cols[header.index("quote")]) if text else None
        printed, pdf, fname = page_at(sources, pos) if pos is not None else (None, None, None)
        if printed:
            cols[pi] = str(printed)
            filled += 1
            print(f"  {cols[0]}  {printed}쪽  ({fname} PDF {pdf}장)")
        else:
            missed += 1
        out.append("\t".join(cols))

    print(f"\n채움 {filled} / 못 찾음 {missed} / 이미 있던 것 {kept}")
    if dry:
        print("(--dry-run 이라 저장하지 않았다)")
        return
    write_text_atomic(TARGET, "\n".join(out) + "\n")
    print("이제 audit 을 돌린다:  python scripts/run.py --from audit")


if __name__ == "__main__":
    main()
