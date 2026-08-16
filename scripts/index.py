"""37개년 백서의 **색인**을 만든다.

    python scripts/index.py                 표로 본다
    python scripts/index.py --year 2010     한 해만 자세히
    python scripts/index.py --write         corpus/index.jsonl 로 저장

**왜 만드나.** 지금은 문장 65,433개가 평평하게 쌓여 있다. 색인이 있으면
'북핵' 을 「제2장 한반도 / 제1절 북핵문제」 로 좁혀 찾을 수 있다.
책장에 이름표를 붙이는 일이다.

**어디서 얻나.** 세 군데를 이 순서로 본다(2026-08-16 전 연도 실측).

    ① 목차파일    파일 이름에 '목차'·'차례' 가 있는 파일          17개년
    ② 본문속목차   장 파일 안에 들어 있는 목차 쪽                16개년
    ③ 본문제목줄   본문에 적힌 '제1절 …' 제목 줄을 모은다         4개년
                  (1997~2000년은 목차가 아예 없다. 원본을 다 열어 확인했다)

**지어내지 않는다.** ③ 도 우리가 만든 제목이 아니라 책이 스스로 붙인
제목을 옮긴 것이다. 그래도 출처가 다르므로 줄마다 `출처` 를 남긴다.
나중에 "이건 어디서 나온 거지?" 를 되짚을 수 있어야 한다.
"""

import argparse
import io
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import etl  # noqa: E402  — 제목 읽는 규칙을 그대로 쓴다

STAGE = PROJECT_ROOT / "etl_test"
OUT = PROJECT_ROOT / "corpus" / "index.jsonl"

# 파일 이름이 목차라고 말하는 것들. 2008년은 '차례' 다.
_TOC_FILE = re.compile(r"목\s*차|차\s*례|contents", re.I)
# 쪽 안에 목차라고 적힌 것. 1989~93 은 한자 '目次' 다.
_TOC_MARK = re.compile(r"^\s*(목\s{0,12}차|目\s{0,12}次|차\s{0,4}례|C\s?O\s?N\s?T\s?E\s?N\s?T\s?S)\s*$")

# 목차 쪽으로 인정할 최소 제목 줄 수. 본문 쪽에도 제목이 하나둘 나오므로
# 여러 개가 몰려 있어야 목차다.
TOC_PAGE_MIN = 3


def heading_lines(lines: list[str]) -> list[tuple[str, int, str | None]]:
    """그 쪽에서 읽어낸 (장|절, 번호, 제목) 목록."""
    out = []
    for i in range(len(lines)):
        for kind in ("장", "절"):
            h = etl.read_heading(lines, i, kind)
            if h:
                out.append((kind, h[0], h[1]))
                break
    return out


def pages_of(year: int) -> list[dict]:
    p = STAGE / str(year) / "pages.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.open(encoding="utf-8")]


# 진짜 목차 쪽은 짧고 제목이 빽빽하다. HWP·DOC 는 파일 하나가 통째로
# '1쪽' 이라, 이 자를 안 대면 본문 전체가 목차 쪽으로 잡힌다
# (1997~2000년이 그렇게 잘못 잡혔다. 그 네 해는 목차가 정말 없다).
TOC_PAGE_MAX_CHARS = 3000


class ChapterWalker:
    """목차를 훑어 내려가며 지금이 몇 장인지 따라간다.

    장 번호가 절 목록 **위에** 따로 적히는 판도 있고, 아예 안 적히는 판도
    있다(2009~2012년 목차 쪽에는 `제1절…제6절` 만 늘어서 있다).

    그럴 때는 **절 번호가 되돌아가는 것**이 장이 바뀐 자리다.
    `제6절` 다음에 `제1절` 이 오면 새 장이 시작된 것이다. 우리가 정하는 게
    아니라 문서의 번호 매김이 알려주는 사실이다."""

    def __init__(self, start: int | None = None):
        self.ch, self.title, self.last_sec = start, None, 0

    def chapter(self, num: int, title: str | None) -> None:
        self.ch, self.title, self.last_sec = num, title, 0

    def section(self, num: int) -> None:
        if self.ch is None or num <= self.last_sec:
            self.ch = (self.ch or 0) + 1
            self.title = None
        self.last_sec = num


# 절에 번호를 안 붙이는 판이 있다. 2003·2004년 목차가 그렇다.
#   '국제 정치∙경제 정세일반 …………… 17'
# 이런 줄은 점선과 쪽번호로 알아본다. 번호는 나온 차례대로 매긴다.
_LEADER = re.compile(r"^\s*(\S[^\n]{3,58}?)\s*[.·…‥]{3,}\s*(\d{1,4})\s*$")
# 번호 붙은 항(1. 2. 가. 나.)은 절이 아니라 그 아래 단계다. 색인이 부풀지
# 않게 뺀다.
_ITEM = re.compile(r"^\s*(\d{1,2}|[가-하])\s*[.)]\s")


def harvest(lines: list[str], pgs: list[int], src_file: str,
            start_chapter: int | None, lock_chapter: bool = False,
            use_leader: bool = False) -> list[dict]:
    """줄 목록에서 장·절을 뽑는다.

    `lock_chapter` 는 파일 이름이 장을 알려줄 때 쓴다(`제3장.pdf`).
    그때는 본문의 절 번호가 되돌아가도 장을 늘리지 않는다 — 파일명이
    본문보다 믿을 만하다. 이걸 안 하면 1994년이 34장으로 부푼다."""
    rows: list[dict] = []
    w = ChapterWalker(start_chapter)
    auto = 0
    for i in range(len(lines)):
        h = etl.read_heading(lines, i, "장")
        if h:
            # 파일명이 장을 알려줄 때는 **그 장의 제목만** 받아 적는다.
            # 본문에 다른 장 번호가 나와도 장을 옮기지 않는다.
            if lock_chapter:
                if h[0] == start_chapter and h[1] and not w.title:
                    w.title = h[1]
                    rows.append({"장": h[0], "장제목": h[1], "절": None,
                                 "절제목": None, "쪽": pgs[i], "출처파일": src_file})
                continue
            w.chapter(h[0], h[1])
            auto = 0
            rows.append({"장": h[0], "장제목": h[1], "절": None, "절제목": None,
                         "쪽": pgs[i], "출처파일": src_file})
            continue
        h = etl.read_heading(lines, i, "절")
        if h:
            if not lock_chapter:
                w.section(h[0])
            auto = h[0]
            rows.append({"장": w.ch, "장제목": w.title, "절": h[0], "절제목": h[1],
                         "쪽": pgs[i], "출처파일": src_file})
            continue
        if use_leader and not _ITEM.match(lines[i]):
            m = _LEADER.match(lines[i])
            if m:
                title = etl._clean_title(m.group(1))
                if title and len(title) >= 4:
                    auto += 1
                    rows.append({"장": w.ch, "장제목": w.title,
                                 "절": auto, "절제목": title,
                                 "쪽": int(m.group(2)), "출처파일": src_file})
    return rows


def body_only(year: int) -> list[dict]:
    """그 해를 **본문 제목줄만으로** 만든 색인. 채점할 때 쓴다.

    목차가 있는 해에도 이것을 따로 만들어 목차와 맞대보면, 목차가 없는
    해(1997~2000)에 쓴 방법이 얼마나 믿을 만한지 숫자로 나온다."""
    return collect(year, force="본문제목줄")[0]


def _named(rows: list[dict]) -> int:
    """제목까지 붙은 절이 몇 개인가. 어느 쪽이 더 온전한지 재는 자."""
    return len([r for r in rows if r["절"] is not None and r["절제목"]])


def collect(year: int, force: str | None = None) -> tuple[list[dict], str]:
    """그 해의 색인과, 어디서 얻었는지.

    `force` 를 주면 그 출처만 쓴다. 채점(`audit_index.py`)에 쓰인다."""
    pages = pages_of(year)
    if not pages:
        return [], "없음"
    admin = pages[0].get("정권")

    # 파일별로 줄을 이어 붙인다. 쪽 경계에서 제목이 잘리지 않게 한다.
    by_file: dict[str, list[str]] = defaultdict(list)
    page_at: dict[str, list[int]] = defaultdict(list)
    for p in pages:
        f = p["출처파일"]
        for ln in (p.get("원문") or "").splitlines():
            by_file[f].append(ln)
            page_at[f].append(p["쪽"])

    def file_chapter(f: str) -> int | None:
        return etl.classify(Path(f).stem)[1]

    # ① 목차 전용 파일
    rows1 = []
    for f in [x for x in by_file if _TOC_FILE.search(x)]:
        rows1 += harvest(by_file[f], page_at[f], f, None, use_leader=True)

    # ② 본문 파일 안의 목차 쪽 — 짧고 제목이 몰려 있는 쪽만 고른다.
    # **쪽들을 순서대로 이어붙여 한 번에 훑는다.** 펼침면은 좌·우 반쪽으로
    # 나뉘어 들어오는데, 반쪽마다 따로 훑으면 장 번호가 매번 1부터 다시
    # 시작해 다른 장의 절이 한데 섞인다(2010년에 실제로 그랬다).
    # 파일마다 따로 만들어 보고 **가장 온전한 하나**만 쓴다. 파일을 다 합치면
    # 다른 장 표제지의 절이 같은 (장,절) 자리를 다투어 앞 절을 덮는다.
    streams: dict[str, list[tuple[str, int]]] = {}
    for f in by_file:
        if _TOC_FILE.search(f):
            continue
        s: list[tuple[str, int]] = []
        for p in pages:
            if p["출처파일"] != f:
                continue
            text = p.get("원문") or ""
            if len(text) > TOC_PAGE_MAX_CHARS:
                continue
            lines = text.splitlines()
            if len(heading_lines(lines)) < TOC_PAGE_MIN and \
                    not any(_TOC_MARK.match(x) for x in lines):
                continue
            s += [(ln, p["쪽"]) for ln in lines]
        if s:
            streams[f] = s

    def restarts(s: list[tuple[str, int]]) -> int:
        """절 번호가 몇 번 1로 되돌아가나. 두 번 넘으면 **책 전체 목차**다."""
        lines = [x for x, _ in s]
        nums = [h[0] for h in (etl.read_heading(lines, i, "절")
                               for i in range(len(lines))) if h]
        return sum(1 for a, b in zip(nums, nums[1:]) if b <= a)

    whole = {f: s for f, s in streams.items() if restarts(s) >= 2}
    if whole:
        # 가) 책 전체 목차가 든 파일이 있다 — **그 파일 하나만** 쓴다.
        #     다른 파일의 표제지를 섞으면 같은 (장,절) 자리를 다투어
        #     다른 장의 절이 이 장 것으로 바뀐다(2010년에 실제로 그랬다).
        rows2 = max((harvest([x for x, _ in s], [y for _, y in s], f, None,
                             use_leader=True) for f, s in whole.items()),
                    key=_named, default=[])
    else:
        # 나) 장마다 표제지에 그 장의 절 목록만 있는 판 — 파일을 모으되
        #     **파일명이 알려준 장에 묶는다**(2014·2016·2018년).
        rows2 = []
        for f, s in streams.items():
            ch = file_chapter(f)
            rows2 += harvest([x for x, _ in s], [y for _, y in s], f, ch,
                             lock_chapter=ch is not None, use_leader=True)

    # ③ 본문 제목줄 — 파일명이 장을 알려주면 그것을 믿는다.
    # **목차 쪽은 뺀다.** 장 파일 안에 책 전체 목차가 들어 있는 판이 있어
    # (2009~2012년 제1장.pdf 4쪽), 그대로 두면 다른 장의 절이 이 장 것으로
    # 섞인다. 목차는 ② 에서 따로 다룬다.
    body: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for p in pages:
        text = p.get("원문") or ""
        lines = text.splitlines()
        if len(text) <= TOC_PAGE_MAX_CHARS and (
                len(heading_lines(lines)) >= TOC_PAGE_MIN
                or any(_TOC_MARK.match(x) for x in lines)):
            continue
        for ln in lines:
            body[p["출처파일"]].append((ln, p["쪽"]))
    rows3 = []
    for f, items in body.items():
        if _TOC_FILE.search(f):
            continue
        ch = file_chapter(f)
        rows3 += harvest([x for x, _ in items], [y for _, y in items], f, ch,
                         lock_chapter=ch is not None)

    # **셋을 다 만들어 보고 가장 온전한 것을 고른다.**
    # 연도로 나누지 않는 까닭은, 같은 해에도 목차 파일이 OCR 로 깨져
    # 본문보다 부실한 경우가 있기 때문이다(1990년 목차파일 6절 · 본문 21절).
    # 무엇을 골랐는지는 `출처` 칸에 남는다.
    cands = [
        (dedupe(rows1, year, admin, "목차파일"), "① 목차파일"),
        (dedupe(rows2, year, admin, "본문속목차"), "② 본문속 목차쪽"),
        (dedupe(rows3, year, admin, "본문제목줄"), "③ 본문 제목줄"),
    ]

    if force:
        for rs, where in cands:
            if rs and rs[0]["출처"] == force:
                return rs, where
        return [], "없음"

    best = max(cands, key=lambda c: _named(c[0]))
    return best if _named(best[0]) else ([], "없음")


def dedupe(rows: list[dict], year: int, admin: str, source: str) -> list[dict]:
    """같은 장·절이 여러 번 나오면 **제목이 있는 것**을 남긴다.

    쪽 머리글로 같은 제목이 되풀이되므로 그대로 두면 색인이 부푼다."""
    best: dict[tuple, dict] = {}
    for r in rows:
        key = (r["장"], r["절"])
        old = best.get(key)
        title = r["절제목"] if r["절"] is not None else r["장제목"]
        old_title = old and (old["절제목"] if old["절"] is not None else old["장제목"])
        if old is None or (title and not old_title) or (
                title and old_title and len(title) > len(old_title)):
            best[key] = r
    out = []
    for (ch, sec), r in sorted(best.items(), key=lambda kv: (kv[0][0] or 99, kv[0][1] or 0)):
        out.append({
            "연도": year, "정권": admin,
            "장": ch, "장제목": r["장제목"], "절": sec, "절제목": r["절제목"],
            "쪽": r["쪽"], "출처": source, "출처파일": r["출처파일"],
        })
    return out


def main() -> None:
    if __name__ == "__main__":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, help="한 해만 자세히 본다")
    ap.add_argument("--write", action="store_true", help="corpus/index.jsonl 로 저장")
    ap.add_argument("--stage", help="ETL 산출물 폴더 (기본 etl_test)")
    a = ap.parse_args()

    if a.stage:
        global STAGE
        STAGE = Path(a.stage)

    years = [a.year] if a.year else list(range(1989, 2026))
    all_rows, summary = [], []
    for y in years:
        rows, where = collect(y)
        all_rows.extend(rows)
        chs = len({r["장"] for r in rows if r["장"] is not None})
        secs = len([r for r in rows if r["절"] is not None])
        named = len([r for r in rows if r["절"] is not None and r["절제목"]])
        summary.append((y, where, chs, secs, named, rows))

    if a.year:
        y, where, chs, secs, named, rows = summary[0]
        print(f"{y}년 · {where} · 장 {chs}개 · 절 {secs}개\n")
        for r in rows:
            if r["절"] is None:
                print(f"  제{r['장']}장  {r['장제목'] or '(제목 없음)'}")
            else:
                print(f"     제{r['절']}절  {r['절제목'] or '(제목 없음)'}"
                      f"    {r['쪽']}쪽")
        return

    print(f"{'연도':<6}{'어디서':<16}{'장':>4}{'절':>5}{'제목붙은절':>11}  비율")
    print("-" * 56)
    for y, where, chs, secs, named, _ in summary:
        rate = f"{100*named/secs:.0f}%" if secs else "-"
        print(f"{y:<6}{where:<16}{chs:>4}{secs:>5}{named:>11}  {rate:>5}")

    tot_sec = sum(s[3] for s in summary)
    tot_named = sum(s[4] for s in summary)
    print("-" * 56)
    print(f"합계   절 {tot_sec}개 · 제목 붙은 것 {tot_named}개 "
          f"({100*tot_named/max(tot_sec,1):.1f}%)")
    c = Counter(s[1] for s in summary)
    for k, v in c.most_common():
        print(f"  {k:<16} {v}개년")

    if a.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("w", encoding="utf-8") as f:
            for r in all_rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"\n→ {OUT}  ({len(all_rows)}줄)")


if __name__ == "__main__":
    main()
