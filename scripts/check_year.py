"""
[3e] check_year — 한 해가 끝났는지 확인한다.

연도 하나를 다 옮겨 적고 나면 "이 해는 끝났다"고 말할 수 있어야 한다.
audit 은 전체를 훑어 무엇이 문제인지 알려주지만, 방금 끝낸 한 해가
온전한지는 그 안에 묻힌다. 이 도구는 한 해만 처음부터 끝까지 본다.

여덟 가지를 본다
    1  원본 텍스트가 있는가
    2  발간분 대장에 행이 있고 상태·표기방식이 아는 값인가
    3  항목이 있는가 (상태와 앞뒤가 맞는가)
    4  인쇄된 번호가 1..N 으로 이어지는가
    5  제목과 인용문이 원문에 글자 그대로 있는가
    6  인용문이 제목뿐인 항목은 없는가
    7  출처 쪽수가 다 있는가
    8  줄기(stream)가 다 배정됐는가

실행
    python scripts/check_year.py 2013
    python scripts/check_year.py 2013 2014 2015
    python scripts/check_year.py --all        # 26개년 한 줄씩
"""

import io
import sys

from audit import VALID_MARK_STYLE, VALID_STATUS, _LEAD_MARK
from normalize import normalize_for_match
from stage_io import PROJECT_ROOT
from verify import contains_in_order, read_tsv

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

TEXT_ROOT = PROJECT_ROOT / "text"
AUTHORING = PROJECT_ROOT / "authoring"

# 항목이 없어야 정상인 상태
EMPTY_OK = {"blocked", "no-section", "pending"}


def bare(s: str) -> str:
    return normalize_for_match(_LEAD_MARK.sub("", (s or "").strip()))


def check(year: int, ed: dict | None, items: list[dict], streams: set[str]) -> list[tuple[str, str, str]]:
    """(등급, 항목, 설명) 목록. 등급: OK | 미완 | 오류"""
    out: list[tuple[str, str, str]] = []

    txt = TEXT_ROOT / f"{year}.txt"
    if txt.exists():
        raw = txt.read_text(encoding="utf-8")
        out.append(("OK", "원본 텍스트", f"{len(raw):,}자"))
        norm = normalize_for_match(raw)
    else:
        out.append(("오류", "원본 텍스트", "text/ 에 없다 — extract 를 돌려야 한다"))
        return out

    if ed is None:
        out.append(("오류", "발간분 대장", "editions.tsv 에 행이 없다"))
        return out
    st = (ed.get("status") or "").strip()
    ms = (ed.get("markStyle") or "").strip()
    if st not in VALID_STATUS:
        out.append(("오류", "상태", f"'{st}' 는 아는 값이 아니다 — 칸이 밀렸을 수 있다"))
    elif st in EMPTY_OK and not items:
        note = {"blocked": "원본이 없거나 못 읽는다", "no-section": "그 판에 기조 절이 없다",
                "pending": "아직 옮겨 적지 않았다"}[st]
        out.append(("OK" if st != "pending" else "미완", "상태", f"{st} — {note}"))
        if st in ("blocked", "no-section") and not (ed.get("note") or "").strip():
            out.append(("미완", "사유", "화면이 이유를 못 보여준다 — note 를 적어야 한다"))
        return out
    else:
        out.append(("OK", "상태", st))

    if ms not in VALID_MARK_STYLE:
        out.append(("오류", "표기 방식", f"'{ms}' 는 아는 값이 아니다"))
    elif not ms:
        out.append(("미완", "표기 방식", "비어 있다 — 이 값 자체가 자료다"))
    else:
        out.append(("OK", "표기 방식", ms))

    if not items:
        out.append(("오류", "항목", f"상태가 {st} 인데 항목이 하나도 없다"))
        return out
    out.append(("OK", "항목", f"{len(items)}개"))

    ords = sorted(int(i["ordinal"]) for i in items if (i.get("ordinal") or "").strip())
    if ords == list(range(1, len(items) + 1)):
        out.append(("OK", "인쇄된 번호", f"1..{len(items)} 로 이어진다"))
    else:
        out.append(("오류", "인쇄된 번호", f"이어지지 않는다 {ords}"))

    bad = []
    for r in items:
        for field in ("title", "quote"):
            v = (r.get(field) or "").strip()
            if not v:
                bad.append(f"{r['id']}·{field} 비어 있음")
            elif not contains_in_order(norm, v):
                bad.append(f"{r['id']}·{field} 원문에 없음")
    if bad:
        out.append(("오류", "원문 대조", " / ".join(bad[:3]) + (" …" if len(bad) > 3 else "")))
    else:
        out.append(("OK", "원문 대조", f"{len(items) * 2}건 통과"))

    thin = [r["id"] for r in items if bare(r.get("quote")) == bare(r.get("title"))]
    if thin:
        out.append(("미완", "인용문", f"제목뿐인 항목 {len(thin)}개 — {', '.join(thin[:4])}"))
    else:
        out.append(("OK", "인용문", "모두 본문에서 가져왔다"))

    nopage = [r["id"] for r in items if not (r.get("srcPage") or "").strip()]
    if nopage:
        out.append(("미완", "출처 쪽수", f"{len(nopage)}개 비어 있음 — {', '.join(nopage[:4])}"))
    else:
        out.append(("OK", "출처 쪽수", "모두 있다"))

    nostream = [r["id"] for r in items if (r.get("stream") or "").strip() not in streams]
    if nostream:
        out.append(("오류", "줄기", f"{len(nostream)}개가 비었거나 모르는 값 — {', '.join(nostream[:4])}"))
    else:
        out.append(("OK", "줄기", "모두 배정됐다"))

    return out


def main() -> None:
    args = sys.argv[1:]
    ed_rows = read_tsv(AUTHORING / "editions.tsv")
    pr_rows = read_tsv(AUTHORING / "priorities.tsv")
    streams = {r["id"].strip() for r in read_tsv(AUTHORING / "streams.tsv")}
    editions = {int(r["coverageYear"]): r for r in ed_rows}
    by_year: dict[int, list[dict]] = {}
    for r in pr_rows:
        by_year.setdefault(int(r["coverageYear"]), []).append(r)

    years = [int(a) for a in args if a.isdigit()]
    brief = "--all" in args
    if brief:
        years = sorted(editions)
    if not years:
        print("연도를 적어야 한다.  예:  python scripts/check_year.py 2013")
        sys.exit(2)

    mark = {"OK": "OK  ", "미완": "미완 ", "오류": "오류 "}
    failed = 0

    for y in years:
        rows = check(y, editions.get(y), by_year.get(y, []), streams)
        errs = [r for r in rows if r[0] == "오류"]
        todo = [r for r in rows if r[0] == "미완"]
        verdict = "오류" if errs else ("미완" if todo else "끝남")
        if errs:
            failed += 1

        if brief:
            detail = ", ".join(f"{r[1]}" for r in (errs + todo)[:3])
            print(f"{y}  {verdict:<4} {detail}")
            continue

        print(f"\n{'=' * 56}\n  {y}년 — {verdict}\n{'=' * 56}")
        for level, label, msg in rows:
            print(f"  {mark[level]} {label:<10} {msg}")

    if not brief:
        print()
    if failed:
        print(f"오류가 있는 해 {failed}개 — 고치기 전에는 끝난 것이 아니다.")
        sys.exit(1)


if __name__ == "__main__":
    main()
