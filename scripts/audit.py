"""
[0] audit — 전 단계를 한 번에 점검한다. data.json 이 나가기 전 마지막 관문.

각 단계가 저마다 실패를 알리지만 흩어져 있어서, 무엇이 빠졌는지 한눈에 볼 수
없었다. 실제로 editions.tsv 의 칸이 하나 밀려 2016·2021년 status 가 조용히
'pending' 으로 바뀐 것을 한참 뒤에야 발견했다. 이 도구는 그런 일을 그 자리에서
잡는다.

등급
  BLOCK   틀린 자료다. 빌드를 세운다.
  WARN    아직 덜 된 것이다. 진행은 되지만 화면에 구멍이 보인다.
  INFO    알고 있어야 할 사실.

실행
    python scripts/audit.py            # 전 단계 점검
    python scripts/audit.py --strict   # WARN 도 실패로 친다
    python scripts/audit.py --stage authoring
"""

AUDIT_VERSION = "v1.0"

import io
import json
import sys
from pathlib import Path

from normalize import normalize_for_match
from stage_io import PROJECT_ROOT, REPORTS_ROOT, write_json_atomic
from verify import contains_in_order, read_tsv

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DATA_ROOT = PROJECT_ROOT / "data"
TEXT_ROOT = PROJECT_ROOT / "text"
AUTHORING = PROJECT_ROOT / "authoring"

SCOPE_FROM, SCOPE_TO = 1998, 2025

VALID_STATUS = {"verified", "partial", "from-preface", "pending", "blocked", "no-section"}
VALID_MARK_STYLE = {"number", "ordinal-word", "bullet", "inline-lead", "prose",
                    "roman", "circled", "heading", ""}
VALID_FLAGS = {"title-lost", "from-preface", "partial", "ocr", "lead-only",
               "heading-only", "no-quote", "page-break", ""}

# 인용문이 실질적으로 제목뿐인지 볼 때 앞의 번호·글머리 기호는 떼고 본다.
# '1. 북핵문제 진전' 은 '북핵문제 진전' 과 같은 내용이다.
_LEAD_MARK = __import__("re").compile(r"^[\s\d.．)①-⑮ⅠⅡⅢⅣⅤ▲●■◆·]+")
# 항목이 있어서는 안 되는 상태 — 있으면 앞뒤가 안 맞는다
EMPTY_STATUS = {"pending", "blocked", "no-section"}


class Findings:
    def __init__(self):
        self.rows: list[tuple[str, str, str]] = []   # (stage, level, message)

    def add(self, stage, level, msg):
        self.rows.append((stage, level, msg))

    def of(self, stage=None, level=None):
        return [r for r in self.rows
                if (stage is None or r[0] == stage) and (level is None or r[1] == level)]


# ── [1] extract ──────────────────────────────────────────────────────────────

def audit_extract(f: Findings) -> dict:
    years_on_disk = sorted(int(d.name) for d in DATA_ROOT.iterdir()
                           if d.is_dir() and d.name.isdigit())
    scope = [y for y in years_on_disk if SCOPE_FROM <= y <= SCOPE_TO]
    meta_by_year = {}

    for y in scope:
        txt, meta = TEXT_ROOT / f"{y}.txt", TEXT_ROOT / f"{y}.pages.json"
        if not txt.exists() or not meta.exists():
            f.add("extract", "BLOCK", f"{y}: 추출 산출물이 없다 — extract.py 를 돌려야 한다")
            continue
        try:
            m = json.loads(meta.read_text(encoding="utf-8"))
        except Exception as exc:
            f.add("extract", "BLOCK", f"{y}: pages.json 을 읽을 수 없다 ({exc})")
            continue
        meta_by_year[y] = m

        if m.get("chars", 0) < 1000:
            f.add("extract", "BLOCK", f"{y}: 추출된 글자가 {m.get('chars', 0)}자뿐이다")
        failed = [s for s in m["sources"] if s.get("status") == "failed"]
        for s in failed:
            f.add("extract", "WARN", f"{y}: {s['file']} 읽기 실패 — {s.get('error', '')[:60]}")
        if any(s.get("ocr") for s in m["sources"]):
            f.add("extract", "INFO", f"{y}: OCR 유래 — 인용에 오탈자가 섞일 수 있다")

    missing = set(range(SCOPE_FROM, SCOPE_TO + 1)) - set(scope)
    if missing:
        f.add("extract", "BLOCK", f"data/ 에 없는 연도: {sorted(missing)}")
    f.add("extract", "INFO", f"범위 {SCOPE_FROM}~{SCOPE_TO} — {len(meta_by_year)}개년 추출됨")
    return meta_by_year


# ── [2] authoring 정합성 ─────────────────────────────────────────────────────

def audit_authoring(f: Findings, meta_by_year: dict):
    ed_rows = read_tsv(AUTHORING / "editions.tsv")
    pr_rows = read_tsv(AUTHORING / "priorities.tsv")
    st_rows = read_tsv(AUTHORING / "streams.tsv")
    tr_rows = read_tsv(AUTHORING / "transitions.tsv")

    editions = {int(r["coverageYear"]): r for r in ed_rows}
    stream_ids = {r["id"].strip() for r in st_rows}

    if len(editions) != len(ed_rows):
        f.add("authoring", "BLOCK", "editions.tsv 에 연도가 중복된다")
    for y in meta_by_year:
        if y not in editions:
            f.add("authoring", "BLOCK", f"{y}: 추출은 됐는데 editions.tsv 에 행이 없다")

    for y, r in sorted(editions.items()):
        st = (r.get("status") or "").strip()
        ms = (r.get("markStyle") or "").strip()
        if st not in VALID_STATUS:
            f.add("authoring", "BLOCK",
                  f"{y}: status '{st}' 는 아는 값이 아니다 — 칸이 밀렸을 수 있다")
        if ms not in VALID_MARK_STYLE:
            f.add("authoring", "BLOCK", f"{y}: markStyle '{ms}' 는 아는 값이 아니다")
        if st in ("verified", "partial") and not ms:
            f.add("authoring", "WARN", f"{y}: {st} 인데 markStyle 이 비어 있다")
        if st in ("blocked", "no-section") and not (r.get("note") or "").strip():
            f.add("authoring", "WARN", f"{y}: {st} 인데 사유(note)가 없다 — 화면이 이유를 못 보여준다")

    seen_ids: set[str] = set()
    by_year: dict[int, list[dict]] = {}
    for r in pr_rows:
        rid = r["id"].strip()
        if rid in seen_ids:
            f.add("authoring", "BLOCK", f"priorities.tsv 에 id 가 중복된다: {rid}")
        seen_ids.add(rid)
        y = int(r["coverageYear"])
        by_year.setdefault(y, []).append(r)

        if not rid.startswith(str(y)):
            f.add("authoring", "WARN", f"{rid}: id 와 coverageYear({y})가 어긋난다")
        s = (r.get("stream") or "").strip()
        if s and s not in stream_ids:
            f.add("authoring", "BLOCK", f"{rid}: streams.tsv 에 없는 줄기 '{s}'")
        for fl in (r.get("flags") or "").split(";"):
            if fl.strip() and fl.strip() not in VALID_FLAGS:
                f.add("authoring", "WARN", f"{rid}: 모르는 flag '{fl.strip()}'")
        if not (r.get("title") or "").strip():
            f.add("authoring", "BLOCK", f"{rid}: title 이 비어 있다")
        if not (r.get("quote") or "").strip():
            f.add("authoring", "BLOCK", f"{rid}: quote 가 비어 있다")

    for y, items in sorted(by_year.items()):
        r = editions.get(y)
        if r is None:
            f.add("authoring", "BLOCK", f"{y}: editions.tsv 에 없는 연도의 항목이 {len(items)}개 있다")
            continue
        st = (r.get("status") or "").strip()
        if st in EMPTY_STATUS:
            f.add("authoring", "BLOCK",
                  f"{y}: status 가 {st} 인데 항목이 {len(items)}개 있다 — 앞뒤가 안 맞는다")
        ords = sorted(int(i["ordinal"]) for i in items if (i.get("ordinal") or "").strip())
        if ords != list(range(1, len(items) + 1)):
            level = "BLOCK" if st == "verified" else "WARN"
            f.add("authoring", level, f"{y}: 번호가 1..{len(items)} 로 이어지지 않는다 {ords}")

    for y, r in sorted(editions.items()):
        st = (r.get("status") or "").strip()
        if st in ("verified", "partial") and y not in by_year:
            f.add("authoring", "BLOCK", f"{y}: status 가 {st} 인데 항목이 하나도 없다")
        if st == "pending":
            f.add("authoring", "WARN", f"{y}: 아직 옮겨 적지 않았다")

    declared = {int(r["coverageYear"]) for r in tr_rows}
    unknown = declared - set(editions)
    if unknown:
        f.add("authoring", "WARN", f"transitions.tsv 에 editions 없는 연도: {sorted(unknown)}")

    f.add("authoring", "INFO",
          f"발간분 {len(editions)}개년 / 항목 {len(pr_rows)}개 / 줄기 {len(stream_ids)}개")
    return editions, pr_rows


# ── [3] verify (인용 원문 대조) ──────────────────────────────────────────────

def audit_verify(f: Findings, pr_rows: list[dict]):
    cache: dict[int, str] = {}
    checked = 0
    for r in pr_rows:
        y = int(r["coverageYear"])
        if y not in cache:
            p = TEXT_ROOT / f"{y}.txt"
            cache[y] = normalize_for_match(p.read_text(encoding="utf-8")) if p.exists() else ""
        norm = cache[y]
        if not norm:
            f.add("verify", "BLOCK", f"{r['id']}: text/{y}.txt 가 없다")
            continue
        for field in ("title", "quote"):
            v = (r.get(field) or "").strip()
            if not v:
                continue
            checked += 1
            if not contains_in_order(norm, v):
                f.add("verify", "BLOCK", f"{r['id']}·{field}: 원문에 없다 — {v[:50]}…")
    f.add("verify", "INFO", f"원문 대조 {checked}건")


# ── [4] 최종 완결성 (data.json 이 나가기 전) ────────────────────────────────

def audit_final(f: Findings, editions: dict, pr_rows: list[dict]):
    def bare(s: str) -> str:
        return normalize_for_match(_LEAD_MARK.sub("", (s or "").strip()))

    thin = [r for r in pr_rows if bare(r.get("quote")) == bare(r.get("title"))]
    if thin:
        years = sorted({int(r["coverageYear"]) for r in thin})
        f.add("final", "WARN",
              f"인용문이 제목뿐인 항목 {len(thin)}개 — 화면에서 '원문 보기'가 빈 손이 된다 "
              f"({', '.join(map(str, years))})")
    no_page = [r for r in pr_rows if not (r.get("srcPage") or "").strip()]
    if no_page:
        f.add("final", "WARN",
              f"출처 쪽수가 없는 항목 {len(no_page)}개 — 스펙 §8-1 은 쪽까지 요구한다")

    links = AUTHORING / "links.tsv"
    if not links.exists() or not read_tsv(links):
        f.add("final", "WARN", "links 가 비어 있다 — 항목 사이 계승·개명·소멸이 아직 없다")

    done = {int(r["coverageYear"]) for r in pr_rows}
    fillable = {y for y, r in editions.items()
                if (r.get("status") or "").strip() not in ("blocked", "no-section")}
    left = sorted(fillable - done)
    if left:
        f.add("final", "WARN", f"채울 수 있는데 비어 있는 연도: {left}")

    for y, r in sorted(editions.items()):
        st = (r.get("status") or "").strip()
        if st == "blocked":
            f.add("final", "INFO", f"{y}: blocked — 자료를 구하면 채워진다")
        if st == "no-section":
            f.add("final", "INFO", f"{y}: no-section — 그 판에 기조 절이 없다. 영원히 빈칸이다")


# ── 실행 ────────────────────────────────────────────────────────────────────

STAGES = [("extract", "원본 → 텍스트"), ("authoring", "표의 정합성"),
          ("verify", "인용 원문 대조"), ("final", "최종 완결성")]


def completion_table(editions: dict, pr_rows: list[dict]) -> None:
    """연도별로 무엇이 채워졌고 무엇이 비었는지 한눈에.

    WARN 목록은 '무엇이 문제인가'를 알려주지만 '얼마나 남았나'는 안 보인다.
    끝났는지 판단하려면 연도별로 늘어놓고 봐야 한다."""
    by_year: dict[int, list[dict]] = {}
    for r in pr_rows:
        by_year.setdefault(int(r["coverageYear"]), []).append(r)

    def bare(s):
        return normalize_for_match(_LEAD_MARK.sub("", (s or "").strip()))

    print("\n" + "=" * 60)
    print("  연도별 완성도")
    print("=" * 60)
    print(f"{'연도':<6}{'상태':<12}{'항목':>4}{'인용문':>7}{'쪽수':>6}  ")
    print("-" * 46)

    done_all = 0
    for y in sorted(editions):
        st = (editions[y].get("status") or "").strip()
        items = by_year.get(y, [])
        if not items:
            note = {"blocked": "원본 결손", "no-section": "그 판에 없음"}.get(st, "미착수")
            print(f"{y:<6}{st:<12}{'-':>4}{'-':>7}{'-':>6}  {note}")
            continue
        rich = sum(1 for r in items if bare(r.get("quote")) != bare(r.get("title")))
        paged = sum(1 for r in items if (r.get("srcPage") or "").strip())
        n = len(items)
        full = (rich == n and paged == n)
        done_all += full
        bar = "완료" if full else ""
        print(f"{y:<6}{st:<12}{n:>4}{f'{rich}/{n}':>7}{f'{paged}/{n}':>6}  {bar}")

    fillable = [y for y, r in editions.items()
                if (r.get("status") or "").strip() not in ("blocked", "no-section")]
    print("-" * 46)
    print(f"  채울 수 있는 {len(fillable)}개년 중 완전히 끝난 것: {done_all}개년")


def main() -> None:
    strict = "--strict" in sys.argv
    only = None
    if "--stage" in sys.argv:
        only = sys.argv[sys.argv.index("--stage") + 1]

    f = Findings()
    meta = audit_extract(f)
    editions, pr_rows = audit_authoring(f, meta)
    if not f.of("extract", "BLOCK") and not f.of("authoring", "BLOCK"):
        audit_verify(f, pr_rows)
        audit_final(f, editions, pr_rows)
    else:
        f.add("verify", "INFO", "앞 단계가 막혀 건너뜀")

    print(f"audit {AUDIT_VERSION}\n")
    mark = {"BLOCK": "✗", "WARN": "!", "INFO": "·"}
    for stage, label in STAGES:
        if only and stage != only:
            continue
        rows = f.of(stage)
        b, w = len(f.of(stage, "BLOCK")), len(f.of(stage, "WARN"))
        head = "통과" if b == 0 and w == 0 else (f"BLOCK {b}" if b else f"WARN {w}")
        print(f"[{stage}] {label}  —  {head}")
        for _, level, msg in rows:
            if level == "INFO" and (b or w):
                continue          # 문제가 있을 땐 INFO 를 접어둔다
            print(f"   {mark[level]} {msg}")
        print()

    if not only and not f.of("extract", "BLOCK") and not f.of("authoring", "BLOCK"):
        completion_table(editions, pr_rows)

    blocks, warns = f.of(level="BLOCK"), f.of(level="WARN")
    write_json_atomic(REPORTS_ROOT / "audit_report.json", {
        "auditVersion": AUDIT_VERSION,
        "blocks": [{"stage": s, "message": m} for s, _, m in blocks],
        "warns": [{"stage": s, "message": m} for s, _, m in warns],
    })

    print("=" * 60)
    if blocks:
        print(f"BLOCK {len(blocks)}건 — 자료가 틀렸다. 고치기 전에는 build 하지 않는다.")
        sys.exit(1)
    if warns and strict:
        print(f"WARN {len(warns)}건 — --strict 라 실패로 친다.")
        sys.exit(1)
    if warns:
        print(f"BLOCK 0 / WARN {len(warns)}건 — 나갈 수는 있으나 화면에 구멍이 보인다.")
    else:
        print("전 단계 통과. build 해도 좋다.")


if __name__ == "__main__":
    main()
