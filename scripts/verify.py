"""
[4] verify — 이 프로젝트의 심장 (스펙 §7).

`authoring/priorities.tsv` 의 모든 title 과 quote 가 그 해 `text/<연도>.txt` 에
글자 그대로 있는지 확인한다. 하나라도 어긋나면 **빌드를 멈춘다.**

손으로 옮겨 적는 방식의 유일한 약점이 오탈자인데, 그것을 기계가 막는다.
부분 성공으로 넘어가지 않는 것이 요점이다 — 절반만 맞는 자료는 틀린 자료다.

검증할 수 없는 것: stream 배정과 links 의 relation 은 사람의 판단이라
기계가 확인할 방법이 없다. 대신 연결마다 근거 인용을 함께 남긴다.

실행:
    python scripts/verify.py
    python scripts/verify.py 1998 2013      # 특정 연도만
    python scripts/verify.py --show-fail    # 실패한 자리의 원문 주변을 보여준다
"""

import io
import sys
from pathlib import Path

from normalize import normalize_for_match, split_ellipsis
from stage_io import PROJECT_ROOT, REPORTS_ROOT, report_failures, write_json_atomic

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

TEXT_ROOT = PROJECT_ROOT / "text"
AUTHORING = PROJECT_ROOT / "authoring"


def read_tsv(path: Path) -> list[dict]:
    """주석(#)과 빈 줄을 걷어내고 첫 유효 줄을 머리글로 삼는다."""
    rows: list[dict] = []
    header: list[str] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cols = line.split("\t")
        if header is None:
            header = cols
            continue
        # 뒤쪽 빈 칸이 잘려 있어도 관대하게 받는다
        cols += [""] * (len(header) - len(cols))
        rows.append(dict(zip(header, cols)))
    return rows


def contains_in_order(haystack: str, needle: str) -> bool:
    """생략 표시 (…) 로 잘라, 각 조각이 원문에 **순서대로** 나오면 통과."""
    pos = 0
    for piece in split_ellipsis(needle):
        idx = haystack.find(normalize_for_match(piece), pos)
        if idx < 0:
            return False
        pos = idx + len(normalize_for_match(piece))
    return True


def main() -> None:
    args = sys.argv[1:]
    show_fail = "--show-fail" in args
    years = {int(a) for a in args if a.isdigit()}

    pri_path = AUTHORING / "priorities.tsv"
    if not pri_path.exists():
        print(f"[ERROR] {pri_path} 가 없다.")
        sys.exit(1)
    rows = read_tsv(pri_path)
    if years:
        rows = [r for r in rows if int(r["coverageYear"]) in years]
    if not rows:
        print("[ERROR] 검사할 항목이 없다.")
        sys.exit(1)

    cache: dict[int, tuple[str, str]] = {}
    failures: list[tuple[str, str]] = []
    checked = 0

    for r in rows:
        year = int(r["coverageYear"])

        # **스캔에서 사람이 읽어 적은 줄.** 글자 인식이 못 읽는 쪽이 있다
        # (1989~1991년 국한문 혼용 스캔본). 그 쪽은 OCR 글월과 대조할 수 없다.
        #
        # 대조를 못 한다고 그냥 통과시키면 지어내도 아무도 모른다. 그래서
        # **대신 지켜야 할 것**을 요구한다 — 어느 파일 몇 쪽인지 정확히 적을 것.
        # 누구든 그 쪽을 열어 눈으로 확인할 수 있으면 근거는 성립한다.
        if "from-scan" in (r.get("flags") or ""):
            checked += 1
            if not (r.get("srcEdition") or "").strip():
                failures.append((r["id"], "from-scan 인데 srcEdition 이 없다"))
            if not (r.get("srcPage") or "").strip():
                failures.append((r["id"], "from-scan 인데 srcPage 가 없다 — "
                                          "사람이 열어볼 쪽을 반드시 적는다"))
            for field in ("title", "quote"):
                if not (r.get(field) or "").strip():
                    failures.append((r["id"], f"{field} 가 비어 있다"))
            continue

        if year not in cache:
            p = TEXT_ROOT / f"{year}.txt"
            if not p.exists():
                cache[year] = ("", "")
            else:
                raw = p.read_text(encoding="utf-8")
                cache[year] = (raw, normalize_for_match(raw))
        raw, norm = cache[year]
        if not raw:
            failures.append((r["id"], f"text/{year}.txt 가 없다"))
            continue

        for field in ("title", "quote"):
            value = (r.get(field) or "").strip()
            if not value:
                failures.append((r["id"], f"{field} 가 비어 있다"))
                continue
            checked += 1
            if not contains_in_order(norm, value):
                failures.append((r["id"], f"{field} 가 원문에 없다: {value[:60]}…"))
                if show_fail:
                    # 어디까지 맞았는지 보여주면 오탈자 위치를 찾기 쉽다
                    n = normalize_for_match(value)
                    for cut in range(len(n), 4, -1):
                        if n[:cut] in norm:
                            at = norm.find(n[:cut])
                            print(f"\n  [{r['id']}·{field}] 앞 {cut}자까지 일치, 그 뒤가 어긋남")
                            print(f"    적은 것: …{n[max(0, cut - 20):cut + 30]}")
                            print(f"    원문   : …{norm[max(0, at + cut - 20):at + cut + 30]}")
                            break

    print(f"verify — 항목 {len(rows)}개 / 대조 {checked}건")
    by_year: dict[int, list[str]] = {}
    for r in rows:
        by_year.setdefault(int(r["coverageYear"]), []).append(r["id"])
    failed_ids = {i for i, _ in failures}
    print(f"\n{'연도':<6}{'항목':>4}{'결과':>8}")
    print("-" * 20)
    for year in sorted(by_year):
        ids = by_year[year]
        bad = sum(1 for i in ids if i in failed_ids)
        mark = "통과" if bad == 0 else f"실패 {bad}"
        print(f"{year:<6}{len(ids):>4}{mark:>8}")

    write_json_atomic(REPORTS_ROOT / "verify_report.json", {
        "items": len(rows), "checks": checked,
        "failures": [{"id": i, "reason": r} for i, r in failures],
    })

    if failures:
        print(f"\n실패 {len(failures)}건")
        for i, reason in failures[:20]:
            print(f"  {i}\t{reason}")
        report_failures("verify", failures)
        print("\n빌드를 멈춘다. 원문과 다른 것을 고친 뒤 다시 돌린다.")
        sys.exit(1)

    print("\n전건 통과. build 로 넘어가도 된다.")


if __name__ == "__main__":
    main()
