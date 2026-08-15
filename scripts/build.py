"""
[5] build — 검증을 통과한 표들을 data.json 하나로 묶는다.

이 파일이 프런트엔드와의 유일한 접점이다(스펙 §3의 경계). 화면은 이것만 읽고,
어떤 값도 코드에 박지 않는다.

**verify 를 먼저 통과해야 한다.** build 는 검증하지 않는다 — 검증은 verify 의
일이고, 여기서 다시 하면 두 곳이 어긋날 때 어느 쪽이 맞는지 알 수 없게 된다.

실행:
    python scripts/verify.py && python scripts/build.py
"""

BUILD_VERSION = "v1.0"
SCHEMA_VERSION = 1

import io
import sys
from datetime import date
from pathlib import Path

from stage_io import PROJECT_ROOT, write_json_atomic
from verify import read_tsv

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

AUTHORING = PROJECT_ROOT / "authoring"
OUT = PROJECT_ROOT / "data.json"


def _int(v, default=None):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def _nz(v):
    """빈 칸은 null 로. 빈 문자열과 '값 없음'을 화면이 구별해야 한다."""
    v = (v or "").strip()
    return v or None


# 칸이 하나 밀리면 status 자리에 markStyle 값이 들어앉는다. 사람 눈으로는
# 안 잡히고 화면에서 '아직 안 함'으로 조용히 표시된다 — 실제로 겪었다.
# 아는 값만 통과시켜 그 자리에서 세운다.
VALID_STATUS = {"verified", "partial", "from-preface", "pending", "blocked", "no-section"}
VALID_MARK_STYLE = {"number", "ordinal-word", "bullet", "inline-lead", "prose",
                    "roman", "circled", "heading", ""}


def check_editions(editions: list[dict]) -> list[str]:
    problems = []
    for e in editions:
        y = e["coverageYear"]
        if e["status"] not in VALID_STATUS:
            problems.append(f"{y}: status '{e['status']}' 는 아는 값이 아니다 — 칸이 밀렸을 수 있다")
        if (e["markStyle"] or "") not in VALID_MARK_STYLE:
            problems.append(f"{y}: markStyle '{e['markStyle']}' 는 아는 값이 아니다")
    return problems


def check_priorities(priorities: list[dict], editions: list[dict]) -> list[str]:
    """항목이 붙을 발간분이 실제로 있는지, 번호가 1..N 으로 이어지는지."""
    problems = []
    known = {e["coverageYear"]: e for e in editions}
    by_year: dict[int, list[dict]] = {}
    for p in priorities:
        by_year.setdefault(p["coverageYear"], []).append(p)

    for year, items in sorted(by_year.items()):
        if year not in known:
            problems.append(f"{year}: editions 에 없는 연도의 항목이 있다")
            continue
        st = known[year]["status"]
        if st in ("pending", "blocked", "no-section"):
            problems.append(f"{year}: status 가 {st} 인데 항목이 {len(items)}개 있다 — 앞뒤가 안 맞는다")
        ordinals = sorted(p["ordinal"] or 0 for p in items)
        if ordinals != list(range(1, len(ordinals) + 1)) and st == "verified":
            problems.append(f"{year}: 번호가 1..{len(ordinals)} 로 이어지지 않는다 {ordinals}")
    return problems


def main() -> None:
    editions_rows = read_tsv(AUTHORING / "editions.tsv")
    priorities_rows = read_tsv(AUTHORING / "priorities.tsv")
    streams_rows = read_tsv(AUTHORING / "streams.tsv")
    transitions_rows = read_tsv(AUTHORING / "transitions.tsv")

    editions = []
    for r in editions_rows:
        year = _int(r["coverageYear"])
        editions.append({
            "coverageYear": year,
            "title": _nz(r.get("title")),
            "publishedYear": _int(r.get("publishedYear")),
            "administration": _nz(r.get("administration")),
            "brand": _nz(r.get("brand")),
            "section": {
                "chapter": _int(r.get("chapter")),
                "section": _int(r.get("section")),
                "label": _nz(r.get("label")),
                "page": _int(r.get("pages")),
            },
            "markStyle": _nz(r.get("markStyle")),
            "status": _nz(r.get("status")) or "pending",
            "sourceFiles": [x for x in (r.get("sourceFiles") or "").split(";") if x.strip()],
            "note": _nz(r.get("note")),
        })
    editions.sort(key=lambda e: e["coverageYear"])

    priorities = []
    for r in priorities_rows:
        priorities.append({
            "id": r["id"].strip(),
            "coverageYear": _int(r["coverageYear"]),
            "ordinal": _int(r.get("ordinal")),
            "ordinalSource": _nz(r.get("ordinalSource")),
            "title": _nz(r.get("title")),
            "quote": _nz(r.get("quote")),
            "stream": _nz(r.get("stream")),
            "source": {
                "edition": _nz(r.get("srcEdition")),
                "chapter": _int(r.get("srcChapter")),
                "section": _int(r.get("srcSection")),
                "page": _int(r.get("srcPage")),
            },
            "flags": [x for x in (r.get("flags") or "").split(";") if x.strip()],
        })
    priorities.sort(key=lambda p: (p["coverageYear"], p["ordinal"] or 0))

    used_streams = {p["stream"] for p in priorities if p["stream"]}
    streams = []
    for r in streams_rows:
        sid = r["id"].strip()
        members = [p["id"] for p in priorities if p["stream"] == sid]
        streams.append({"id": sid, "label": _nz(r.get("label")),
                        "note": _nz(r.get("note")), "members": members})
    missing = used_streams - {s["id"] for s in streams}
    if missing:
        print(f"[주의] streams.tsv 에 없는 줄기가 쓰였다: {', '.join(sorted(missing))}")

    # 이음매가 적히지 않은 해는 steady 로 채운다 — 대조군을 화면에 같은 형식으로
    # 놓기 위해 **모든 대상 연도에 하나씩** 있어야 한다(스펙 §5).
    declared = {_int(r["coverageYear"]): r for r in transitions_rows}
    transitions = []
    prev_admin = None
    for e in editions:
        y = e["coverageYear"]
        r = declared.get(y)
        if r:
            transitions.append({
                "coverageYear": y, "type": _nz(r.get("type")) or "steady",
                "outgoing": _nz(r.get("outgoing")), "incoming": _nz(r.get("incoming")),
                "date": _nz(r.get("date")), "note": _nz(r.get("note")),
            })
        else:
            transitions.append({
                "coverageYear": y, "type": "steady",
                "outgoing": None, "incoming": e["administration"],
                "date": None, "note": None,
            })
        prev_admin = e["administration"]

    problems = check_editions(editions) + check_priorities(priorities, editions)
    if problems:
        print(f"[중단] 표에 앞뒤가 안 맞는 곳이 {len(problems)}건 있다.\n")
        for p in problems:
            print(f"  {p}")
        print("\n고친 뒤 다시 돌린다.")
        sys.exit(1)

    years = [e["coverageYear"] for e in editions]

    data = {
        "meta": {
            "schemaVersion": SCHEMA_VERSION,
            "buildVersion": BUILD_VERSION,
            "builtAt": date.today().isoformat(),
            "coverage": {
                "from": min(years), "to": max(years),
                "withPriorities": len({p["coverageYear"] for p in priorities}),
                "total": len(editions),
            },
        },
        "editions": editions,
        "priorities": priorities,
        "streams": streams,
        "links": [],   # 연결 판정은 아직. 빈 배열이 '아직 없음'을 뜻한다
        "transitions": transitions,
    }

    write_json_atomic(OUT, data)

    print(f"build {BUILD_VERSION} → {OUT}")
    print(f"  발간분   {len(editions)}개년 ({min(years)}~{max(years)})")
    print(f"  항목     {len(priorities)}개 / {len({p['coverageYear'] for p in priorities})}개년")
    print(f"  줄기     {len(streams)}개")
    print(f"  이음매   {sum(1 for t in transitions if t['type'] != 'steady')}개 "
          f"(나머지 {sum(1 for t in transitions if t['type'] == 'steady')}개년은 steady)")
    print(f"  연결     {len(data['links'])}개 — 아직 판정하지 않음")
    print(f"  크기     {OUT.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
