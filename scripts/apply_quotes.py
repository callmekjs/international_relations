"""
[3c] apply_quotes — 골라낸 인용문을 priorities.tsv 에 일괄 반영한다.

harvest 가 내놓은 후보 중 사람이 고른 것을 `authoring/_quotes.tsv`(id, quote)에
적어두면 이 도구가 해당 행의 quote 칸을 바꾸고 heading-only 플래그를 지운다.

반영 뒤 반드시 verify 를 돌린다 — 옮겨 적다 한 글자만 틀려도 원문과 어긋난다.

실행:
    python scripts/apply_quotes.py            # authoring/_quotes.tsv 를 반영
    python scripts/apply_quotes.py --dry-run  # 무엇이 바뀌는지만 본다
"""

import io
import sys
from pathlib import Path

from stage_io import PROJECT_ROOT, write_text_atomic

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

AUTHORING = PROJECT_ROOT / "authoring"
TARGET = AUTHORING / "priorities.tsv"
PATCH = AUTHORING / "_quotes.tsv"


def main() -> None:
    dry = "--dry-run" in sys.argv
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
            qi = header.index("quote")
            fi = header.index("flags")
            cols[qi] = patches[rid]
            # 인용문이 생겼으니 '소제목만'은 더 이상 사실이 아니다
            flags = [f for f in cols[fi].split(";") if f and f != "heading-only"]
            cols[fi] = ";".join(flags)
            changed += 1
            print(f"  {rid}  {patches[rid][:60]}…")
        out.append("\t".join(cols))

    unseen = set(patches) - {l.split("\t")[0].strip() for l in lines if l and not l.startswith("#")}
    if unseen:
        print(f"\n[주의] priorities.tsv 에 없는 id: {', '.join(sorted(unseen))}")

    if dry:
        print(f"\n(가정) {changed}행이 바뀐다. --dry-run 이라 저장하지 않았다.")
        return

    write_text_atomic(TARGET, "\n".join(out) + "\n")
    print(f"\n{changed}행 반영. 이제 verify 를 돌린다:")
    print("  python scripts/verify.py")


if __name__ == "__main__":
    main()
