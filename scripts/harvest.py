"""
[3b] harvest — 소제목만 있는 항목의 본문 첫 문장을 뽑아 인용 후보로 보여준다.

priorities.tsv 의 상당수는 소제목만 적혀 있다(flags=heading-only). 그러면
화면에서 '원문 보기'를 눌러도 보여줄 것이 없어 스펙 §8-1 을 어긴다.

이 도구는 제목을 원문에서 찾아 그 **뒤에 이어지는 첫 문장**을 후보로 내놓는다.
고르는 것은 사람이다 — 자동으로 tsv 를 고치지 않는다.

실행:
    python scripts/harvest.py 2010 2011
    python scripts/harvest.py --all
"""

import io
import re
import sys

from normalize import normalize_for_match
from stage_io import PROJECT_ROOT
from verify import read_tsv

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

TEXT_ROOT = PROJECT_ROOT / "text"
AUTHORING = PROJECT_ROOT / "authoring"

TAIL = 700           # 제목 뒤로 이만큼 훑는다
SENT_END = re.compile(r"(다|음|것)\.\s")


def first_sentence(s: str) -> str:
    """줄바꿈·공백을 정리하고 첫 문장 하나를 돌려준다."""
    s = re.sub(r"\s+", " ", s).strip()
    m = SENT_END.search(s)
    return s[:m.end()].strip() if m else s[:200].strip()


def prose_score(s: str) -> float:
    """본문다움. 목차·요약표는 숫자와 기호가 많고 종결어미가 없다.

    제목이 본문보다 앞의 '요약 표'에 먼저 나오는 판이 많아(2006·2010·2023),
    처음 만나는 자리를 집으면 표를 가져온다. 가장 본문다운 자리를 고른다."""
    if len(s) < 30:
        return -1
    digits = sum(c.isdigit() for c in s) / len(s)
    marks = sum(c in "①②③④⑤⑥⑦⑧⑨⑩ⅠⅡⅢⅣⅤ·…" for c in s) / len(s)
    ends = len(re.findall(r"(하였다|되었다|했다|이다|한다)\.", s))
    return ends * 3 - digits * 40 - marks * 40


def find_after(text: str, norm: str, title: str) -> str | None:
    """제목이 나오는 자리 중 **뒤에 본문이 이어지는** 곳을 고른다."""
    key = normalize_for_match(title)
    if not key or key not in norm:
        return None
    # 정규화된 위치를 원문 위치로 되돌릴 수 없으므로 원문에서 다시 찾는다.
    pat = re.compile(r"\s*".join(map(re.escape, title.replace(" ", "")[:14])))
    best, best_score = None, 0.0
    for m in pat.finditer(text):
        cand = first_sentence(text[m.end(): m.end() + TAIL])
        if len(cand) < 30 or normalize_for_match(cand) == key:
            continue
        sc = prose_score(cand)
        if sc > best_score:
            best, best_score = cand, sc
    return best


def main() -> None:
    args = sys.argv[1:]
    years = {int(a) for a in args if a.isdigit()}
    rows = read_tsv(AUTHORING / "priorities.tsv")
    if years:
        rows = [r for r in rows if int(r["coverageYear"]) in years]
    rows = [r for r in rows if "heading-only" in (r.get("flags") or "")]
    if not rows:
        print("소제목만 있는 항목이 없다.")
        return

    cache: dict[int, tuple[str, str]] = {}
    cur = None
    for r in rows:
        y = int(r["coverageYear"])
        if y not in cache:
            raw = (TEXT_ROOT / f"{y}.txt").read_text(encoding="utf-8")
            cache[y] = (raw, normalize_for_match(raw))
        raw, norm = cache[y]
        if y != cur:
            print(f"\n{'=' * 76}\n{y}\n{'=' * 76}")
            cur = y
        cand = find_after(raw, norm, r["title"])
        print(f"\n[{r['id']}] {r['title']}")
        print(f"  → {cand if cand else '(본문을 찾지 못함)'}")


if __name__ == "__main__":
    main()
