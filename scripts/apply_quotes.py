"""
[3c] apply_quotes — 골라낸 인용문을 priorities.tsv 에 **항목 단위로 검증하며** 반영한다.

harvest 가 내놓은 후보 중 사람이 고른 것을 `authoring/_quotes.tsv`(id, quote)에
적어두면 이 도구가 해당 행의 quote 칸을 바꾸고 heading-only 플래그를 지운다.

**넣는 그 자리에서 원문과 대조한다.** 어긋나면 그 항목만 되돌리고 나머지는 넣는다.
전에는 다 넣은 뒤에 verify 를 따로 돌렸는데, 그러면 어느 것이 틀렸는지 찾느라
되짚어야 했다. 한 항목이 들어갈 때 바로 확인하는 편이 빠르고 안전하다.

실행:
    python scripts/apply_quotes.py            # authoring/_quotes.tsv 를 반영
    python scripts/apply_quotes.py --dry-run  # 무엇이 바뀌는지만 본다
    python scripts/apply_quotes.py --force    # 대조 실패해도 넣는다 (쓸 일 없어야 한다)
"""

import io
import sys
from pathlib import Path

from normalize import normalize_for_match
from stage_io import PROJECT_ROOT, write_text_atomic
from verify import contains_in_order

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

AUTHORING = PROJECT_ROOT / "authoring"
TEXT_ROOT = PROJECT_ROOT / "text"
TARGET = AUTHORING / "priorities.tsv"
PATCH = AUTHORING / "_quotes.tsv"

_norm_cache: dict[int, str] = {}


def check_against_source(year: int, quote: str) -> bool:
    """이 인용문이 그 해 원문에 글자 그대로 있는가."""
    if year not in _norm_cache:
        p = TEXT_ROOT / f"{year}.txt"
        _norm_cache[year] = normalize_for_match(p.read_text(encoding="utf-8")) if p.exists() else ""
    norm = _norm_cache[year]
    return bool(norm) and contains_in_order(norm, quote)


def main() -> None:
    dry = "--dry-run" in sys.argv
    force = "--force" in sys.argv
    if not PATCH.exists():
        print(f"[ERROR] {PATCH} 가 없다.")
        sys.exit(1)

    patches: dict[str, str] = {}
    for line in PATCH.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) >= 2 and cols[1].strip():
            patches[cols[0].strip()] = cols[1].strip()
    if not patches:
        print("반영할 것이 없다.")
        return

    lines = TARGET.read_text(encoding="utf-8").splitlines()
    header: list[str] | None = None
    out: list[str] = []
    changed = 0
    rejected: list[str] = []

    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            out.append(line)
            continue
        cols = line.split("\t")
        if header is None:
            header = cols
            out.append(line)
            continue

        rid = cols[0].strip()
        if rid in patches:
            cols += [""] * (len(header) - len(cols))
            year = int(cols[header.index("coverageYear")])
            ok = check_against_source(year, patches[rid])
            if ok or force:
                qi = header.index("quote")
                fi = header.index("flags")
                cols[qi] = patches[rid]
                # 인용문이 생겼으니 '소제목만'은 더 이상 사실이 아니다
                flags = [f for f in cols[fi].split(";") if f and f != "heading-only"]
                cols[fi] = ";".join(flags)
                changed += 1
                mark = "OK  " if ok else "강제"
                print(f"  {mark} {rid}  {patches[rid][:55]}…")
            else:
                rejected.append(rid)
                print(f"  ✗    {rid}  원문과 다르다 — 넣지 않았다")
                print(f"       적은 것: {patches[rid][:70]}")
        out.append("\t".join(cols))

    unseen = set(patches) - {l.split("\t")[0].strip() for l in lines if l and not l.startswith("#")}
    if unseen:
        print(f"\n[주의] priorities.tsv 에 없는 id: {', '.join(sorted(unseen))}")

    if dry:
        print(f"\n(가정) {changed}행이 바뀐다. --dry-run 이라 저장하지 않았다.")
        return

    write_text_atomic(TARGET, "\n".join(out) + "\n")
    print(f"\n반영 {changed}행 / 거절 {len(rejected)}행")
    if rejected:
        print(f"거절된 항목: {', '.join(rejected)}")
        print("원문을 다시 보고 고친 뒤 다시 넣는다. 넣은 것들은 이미 대조를 통과했다.")
    else:
        print("넣은 항목 전부가 원문 대조를 통과했다.")


if __name__ == "__main__":
    main()
