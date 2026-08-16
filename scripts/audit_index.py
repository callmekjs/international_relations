"""색인이 얼마나 맞는지 **채점한다**.

    python scripts/audit_index.py

**왜 채점이 필요한가.** 색인을 세 군데에서 얻는다(`index.py` 참고).
그중 ③ '본문 제목줄' 은 목차 카드가 없는 해에 본문에 적힌 제목을 모아
되만든 것이다. 지어낸 것은 아니지만 **목차만큼 믿을 수 있는지는 재봐야
안다.**

**어떻게 재나.** 목차가 있는 해에서는 두 가지를 다 만들 수 있다.

    목차가 말하는 절 제목      ← 정답지
    본문 제목줄로 되만든 것    ← 재려는 방법

둘을 맞대 일치율을 낸다. 그 방법을 목차 없는 해(1997~2000)에 쓰는 것이니
"아마 맞을 것" 이 아니라 "○○% 맞았던 방법" 이라고 말할 수 있다.

**맞다고 보는 기준.** 글자가 똑같기를 요구하지 않는다. OCR 오탈자와
띄어쓰기 차이가 있기 때문이다. 제목에서 한글·한자만 남겨 견주고,
한쪽이 다른 쪽에 들어 있으면 맞은 것으로 센다.
"""

import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import index as IX  # noqa: E402

_KEEP = re.compile(r"[^가-힣一-鿿0-9A-Za-z]")


def norm(s: str | None) -> str:
    return _KEEP.sub("", s or "")


def similar(a: str, b: str) -> bool:
    """한쪽이 다른 쪽에 들어 있으면 같은 제목으로 본다."""
    a, b = norm(a), norm(b)
    if not a or not b:
        return False
    if a == b:
        return True
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) < 4:
        return False
    return short in long


def sections(rows: list[dict]) -> dict[tuple, str]:
    return {(r["장"], r["절"]): r["절제목"]
            for r in rows if r["절"] is not None and r["절제목"]}


def main() -> None:
    if __name__ == "__main__":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if len(sys.argv) > 1 and sys.argv[1] == "--stage":
        IX.STAGE = Path(sys.argv[2])

    print("목차가 있는 해에서, 본문으로 되만든 색인이 얼마나 맞나\n")
    print(f"{'연도':<6}{'정답지':>7}{'되만듦':>8}{'맞음':>7}{'놓침':>7}{'덧붙음':>8}  일치율")
    print("-" * 60)

    tot_gold = tot_hit = tot_extra = 0
    scored = []
    for y in range(1989, 2026):
        pages = IX.pages_of(y)
        if not pages:
            continue
        rows, where = IX.collect(y)
        if where.startswith("③"):
            continue                    # 정답지가 없는 해
        gold = sections(rows)

        # 같은 해를 '본문 제목줄' 로만 다시 만든다
        mine = sections(IX.body_only(y))
        if not gold or not mine:
            continue

        hit = 0
        for k, t in gold.items():
            if any(similar(t, u) for u in mine.values()):
                hit += 1
        extra = 0
        for k, u in mine.items():
            if not any(similar(u, t) for t in gold.values()):
                extra += 1
        miss = len(gold) - hit
        rate = 100 * hit / len(gold)
        scored.append((y, len(gold), len(mine), hit, miss, extra, rate))
        tot_gold += len(gold)
        tot_hit += hit
        tot_extra += extra
        print(f"{y:<6}{len(gold):>7}{len(mine):>8}{hit:>7}{miss:>7}{extra:>8}  {rate:5.0f}%")

    print("-" * 60)
    if tot_gold:
        print(f"합계   정답 {tot_gold}개 중 {tot_hit}개를 본문으로 되찾음 "
              f"({100*tot_hit/tot_gold:.1f}%)")
        print(f"       목차에 없는데 본문에서 나온 것 {tot_extra}개")
        print()
        print("이 숫자가 곧 1997~2000년 색인의 신뢰도다 —")
        print("목차가 없어 본문으로 되만든 네 해에 같은 방법을 썼다.")


if __name__ == "__main__":
    main()
