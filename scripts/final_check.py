"""
점검 2층 — 분석·지식그래프에 넣기 전 마지막 관문.

    python scripts/final_check.py
    python scripts/final_check.py --corpus corpus_test --sample 30

1층(check.py)은 **한 해가 온전한가**를 본다. 2층은 **합쳐 놓은 것이 쓸 만한가**를
본다. 연도별로는 다 통과했는데 합치고 보니 정권 하나가 통째로 비었다거나,
한글 칸이 없다거나 하는 일을 여기서 잡는다.

표본 감사는 **무작위가 아니라 수상한 것 먼저** 본다. 무작위 30개는 대개 멀쩡한
것만 나온다. 가장 짧은 것·가장 긴 것·깨진 글자가 있는 것을 우선 보여준다.
"""

import argparse
import io
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from stage_io import PROJECT_ROOT, write_json_atomic   # noqa: E402

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ADMIN_ORDER = ["노태우", "김영삼", "김대중", "노무현", "이명박",
               "박근혜", "문재인", "윤석열", "이재명"]

# 한국 공문서에 나올 리 없는 글자 — 폰트 오추출·디코딩 실패의 흔적
# 글자를 그대로 쓰면 안 된다. 호환용 한자(U+F900~)와 일반 한자(U+8C48 등)는
# 눈으로 구별되지 않아, 범위 끝을 잘못 집으면 한글 전체가 걸린다.
# 실제로 그렇게 써서 "깨진 글자 60.9%" 라는 거짓 경보가 났다(2026-08-15).
BAD_CHARS = re.compile("[㐀-䶿豈-﫿㄰-㆏]")
BAD_RATIO_WARN = 0.001      # 0.1%
BAD_RATIO_FAIL = 0.01       # 1%


def audit(rows: list[dict], n: int) -> list[tuple[str, dict]]:
    """수상한 것 먼저. 무작위는 마지막에 조금만."""
    picks: list[tuple[str, dict]] = []
    body = [r for r in rows if r.get("단위", "문장") == "문장"]
    if not body:
        return picks
    by_len = sorted(body, key=lambda r: len(r["원문"]))
    bad = [r for r in body if BAD_CHARS.search(r["원문"])]

    for r in by_len[:n // 4]:
        picks.append(("가장 짧음", r))
    for r in by_len[-(n // 4):]:
        picks.append(("가장 김", r))
    for r in bad[:n // 4]:
        picks.append(("깨진 글자", r))
    rest = n - len(picks)
    if rest > 0:
        picks += [("무작위", r) for r in random.sample(body, min(rest, len(body)))]
    return picks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="corpus")
    ap.add_argument("--sample", type=int, default=20, help="표본 감사 개수")
    ap.add_argument("--strict", action="store_true", help="미완도 실패로 친다")
    a = ap.parse_args()
    random.seed(0)

    root = PROJECT_ROOT / a.corpus
    if not (root / "index.json").exists():
        print(f"[ERROR] {root} 가 없다. corpus.py 를 먼저 돌린다.")
        sys.exit(1)

    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    rows = [json.loads(l) for l in
            (root / "sentences.jsonl").read_text(encoding="utf-8").splitlines()]

    findings: list[tuple[str, str, str]] = []

    def add(level, label, msg):
        findings.append((level, label, msg))

    # 1. 정권 배정 — 빠진 정권이 있나
    admins = Counter(r.get("정권") for r in rows)
    if None in admins:
        add("오류", "정권 배정", f"정권이 없는 레코드 {admins[None]}개")
    present = [x for x in ADMIN_ORDER if admins.get(x)]
    add("OK", "정권", f"{len(present)}개 — {', '.join(present)}")

    # 2. 계층 — 장·절·쪽이 붙어 있나 (본문만)
    body = [r for r in rows if r.get("단위", "문장") == "문장"]
    for field, limit in (("장", 0.15), ("쪽", 0.0)):
        miss = sum(1 for r in body if not r.get(field))
        ratio = miss / len(body) if body else 0
        lvl = "오류" if ratio > limit else ("미완" if miss else "OK")
        add(lvl, f"{field} 배정", f"없는 본문 {miss}개 ({ratio*100:.1f}%)")

    # 3. 한자 칸 — 원문·한글이 둘 다 있나
    no_ko = sum(1 for r in rows if "한글" not in r)
    if no_ko:
        add("오류", "한글 칸", f"{no_ko}개 레코드에 한글 칸이 없다")
    else:
        changed = sum(1 for r in rows if r["한글"] != r["원문"])
        add("OK", "한글 칸", f"모든 레코드에 있음 · 한자 변환된 것 {changed}개")

    # 4. 깨진 글자 — 폰트 오추출·디코딩 실패
    total_chars = sum(len(r["원문"]) for r in rows)
    bad = sum(len(BAD_CHARS.findall(r["원문"])) for r in rows)
    ratio = bad / total_chars if total_chars else 0
    lvl = "오류" if ratio > BAD_RATIO_FAIL else ("미완" if ratio > BAD_RATIO_WARN else "OK")
    add(lvl, "깨진 글자", f"{bad}개 / {total_chars:,}자 ({ratio*100:.3f}%)")

    # 5. OCR 표시 — 분석 때 감안해야 할 자료가 표시돼 있나
    ocr = index["counts"]["ocrDerived"]
    add("OK", "OCR 표시", f"{ocr:,}개 레코드가 OCR 유래로 표시됨")

    # 6. 중복 — 같은 문장이 여러 번 들어갔나
    seen = Counter(r["원문"] for r in body)
    dup = sum(c - 1 for c in seen.values() if c > 1)
    ratio = dup / len(body) if body else 0
    lvl = "오류" if ratio > 0.10 else ("미완" if ratio > 0.03 else "OK")
    add(lvl, "중복", f"중복 문장 {dup}개 ({ratio*100:.1f}%)")

    # 7. 정권별 균형 — 한 정권이 통째로 비었나
    for a_ in present:
        n = admins[a_]
        if n < 100:
            add("미완", "정권 분량", f"{a_} 가 {n}개뿐이다 — 연도가 덜 들어갔을 수 있다")

    mark = {"OK": "OK  ", "미완": "미완 ", "오류": "오류 "}
    print(f"점검 2층 — {a.corpus}\n{'=' * 60}")
    for lvl, label, msg in findings:
        print(f"  {mark[lvl]} {label:<10} {msg}")

    print(f"\n{'=' * 60}\n  표본 감사 — 수상한 것 먼저\n{'=' * 60}")
    for why, r in audit(rows, a.sample):
        head = f"[{why}] {r['연도']}년 {r.get('정권','')} 장{r.get('장')} {r.get('쪽')}쪽 {len(r['원문'])}자"
        print(f"\n  {head}")
        print(f"    {r['원문'][:150]}")

    write_json_atomic(PROJECT_ROOT / "reports" / "final_check.json", {
        "corpus": a.corpus,
        "findings": [{"level": l, "label": lb, "message": m} for l, lb, m in findings],
    })

    errs = [f for f in findings if f[0] == "오류"]
    warns = [f for f in findings if f[0] == "미완"]
    print(f"\n{'=' * 60}")
    if errs:
        print(f"  오류 {len(errs)}건 — 분석에 넣으면 안 된다.")
        sys.exit(1)
    if warns and a.strict:
        print(f"  미완 {len(warns)}건 — --strict 라 실패로 친다.")
        sys.exit(1)
    print(f"  오류 0 / 미완 {len(warns)}건 — 분석·지식그래프에 넣어도 좋다.")


if __name__ == "__main__":
    main()
