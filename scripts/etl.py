"""
전문 ETL — 한 해를 통째로 뽑는다.

    python scripts/etl.py --year 2013
    python scripts/etl.py --year 2013 --out etl_test
    python scripts/etl.py --year 2013 --force

한 번에 한 해만 다룬다. 검사(check.py)를 통과하지 못하면 그 해 폴더를 지우고
원인을 고친 뒤 그 해만 다시 돌린다. 37개년을 다 뽑아놓고 검사하면, 문제가
나올 때마다 전량을 다시 뽑아야 한다 — 2026-08-15 에 실제로 세 번 그랬다.

산출물  <out>/<연도>/
    pages.jsonl        쪽 하나가 한 줄. 원문 그대로
    paragraphs.jsonl   문단 하나가 한 줄. 장·절·쪽이 함께 붙는다
    meta.json          그 해 정보 + 기준선 숫자

기조 절만 뽑던 옛 extract.py 와는 별개 파일이다. 파일럿이 잘못돼도
지금 쓰는 파이프라인이 그대로 살아 있어야 한다.
"""

ETL_VERSION = "v0.1"

import argparse
import io
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from dehead import strip_pages          # noqa: E402
from formats import read_any            # noqa: E402
from stage_io import PROJECT_ROOT, write_json_atomic  # noqa: E402

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DATA_ROOT = PROJECT_ROOT / "data"
READABLE = {".pdf", ".hwp", ".doc"}

# 어느 해가 어느 정권인가. 연도는 **대상 연도**다(「2014 외교백서」는 2013년).
ADMINISTRATIONS = [
    ("노태우", 1989, 1992), ("김영삼", 1993, 1997), ("김대중", 1998, 2002),
    ("노무현", 2003, 2007), ("이명박", 2008, 2012), ("박근혜", 2013, 2016),
    ("문재인", 2017, 2021), ("윤석열", 2022, 2024), ("이재명", 2025, 2025),
]

# 파일명 → 역할. 연도별 예외표를 두지 않고 이름 생김새만으로 가른다.
_RE_APPENDIX = re.compile(r"부록")
_RE_FRONT = re.compile(r"발간사|머리말|목차|표지|인사말")
_RE_CHAPTER = (
    re.compile(r"제\s*(\d{1,2})\s*장"),
    re.compile(r"[(\-_\s](\d{1,2})\s*장"),
    re.compile(r"\s(\d{2})$"),
)

# 본문에서 장·절이 바뀌는 자리. 공백이 사라진 추출본도 잡히게 열어둔다.
_MARK_CHAPTER = re.compile(r"제\s*(\d{1,2})\s*장\s*([^\n]{0,40})")
_MARK_SECTION = re.compile(r"제\s*(\d{1,2})\s*절\s*([^\n]{0,40})")

# 문단으로 인정할 최소 길이. 이보다 짧으면 제목·쪽번호 잔해일 가능성이 높다.
MIN_PARA_CHARS = 25   # 문장 단위라 문단보다 짧다


def administration(year: int) -> str | None:
    for name, lo, hi in ADMINISTRATIONS:
        if lo <= year <= hi:
            return name
    return None


def classify(stem: str) -> tuple[str, int | None]:
    if _RE_APPENDIX.search(stem):
        return "appendix", None
    for pat in _RE_CHAPTER:
        m = pat.search(stem)
        if m:
            return "chapter", int(m.group(1))
    if _RE_FRONT.search(stem):
        return "front", None
    return "whole", None


def sort_key(role: str, chapter: int | None) -> tuple[int, int]:
    return ({"front": 0, "chapter": 1, "whole": 2, "appendix": 3}.get(role, 9), chapter or 0)


def select_files(year: int) -> list[tuple[Path, str, int | None]]:
    """그 해의 **모든** 읽을 수 있는 파일. 부록도 포함한다 — 전문을 뽑는 것이다."""
    folder = DATA_ROOT / str(year)
    picked = []
    for f in sorted(folder.iterdir()):
        if f.is_file() and f.suffix.lower() in READABLE:
            role, ch = classify(f.stem)
            picked.append((f, role, ch))
    picked.sort(key=lambda t: sort_key(t[1], t[2]))
    return picked


# 한국어 공문서의 문장 끝. 이 형태들로 끝나고 뒤에 공백이 오면 문장이 끊긴다.
_SENT_END = re.compile(r"(?<=다\.)\s|(?<=다\.\”)\s|(?<=음\.)\s|(?<=임\.)\s|(?<=함\.)\s")

# 목차·표 잔해를 걸러낸다. 점선이 길게 이어지거나 숫자만 있는 줄이다.
_TOC_LINE = re.compile(r"[.·…]{5,}|^\s*[\d\s.·]+$")

# 목차 한 줄:  제목 …… 쪽번호
#
# 앞서 `(.{4,60}?)\s*[.·…\s]{2,}\s*` 로 썼다가 물렸다(2026-08-15).
# 가운데 `\s` 가 앞뒤 `\s*` 와 겹쳐서, 안 맞는 긴 줄을 만나면 경우의 수가
# 폭발해 10분을 넘겨도 안 끝났다. 점선 문자만 요구해 겹침을 없앤다.
_TOC_ENTRY = re.compile(r"^\s*(\S[^\n]{2,58}?)[.·…]{2,}\s*(\d{1,3})\s*$")
_TOC_MAX_LINE = 120        # 이보다 긴 줄은 목차가 아니다. 먼저 걸러 시간을 아낀다
# 그 줄이 몇 장·몇 절인지
_TOC_CH = re.compile(r"제\s*(\d{1,2})\s*장")
_TOC_SEC = re.compile(r"제\s*(\d{1,2})\s*절")
# 한 쪽에 목차 줄이 이만큼 있으면 그 쪽은 목차다
TOC_MIN_LINES = 4

# 표 한 줄로 인정할 최소 길이. 부록은 국가명·날짜·숫자라 문장보다 짧다.
MIN_TABLE_CHARS = 8


def parse_toc(page: dict, file_chapter: int | None = None) -> list[dict]:
    """목차 쪽에서 '제목 → 쪽번호' 를 뽑는다.

    목차를 버리지 않는 이유는, 이것이 **본문에 장·절이 다 있는지 검사할
    근거**가 되기 때문이다. 문서가 스스로 밝힌 구조라 우리가 추측할 필요가 없다.

    장 번호는 절 목록 **위에** 따로 적혀 있다. 그래서 쪽을 훑어 내려가며
    마지막으로 본 장을 이어서 붙인다. 그것도 없으면 파일명이 알려준 장을 쓴다."""
    entries = []
    cur_ch = file_chapter
    for line in page["text"].splitlines():
        if len(line) > _TOC_MAX_LINE:
            continue
        ch_here = _TOC_CH.search(line)
        if ch_here:
            cur_ch = int(ch_here.group(1))

        m = _TOC_ENTRY.match(line)
        if not m:
            continue
        title, pg = m.group(1).strip(), int(m.group(2))
        if not title or pg > 2000:
            continue
        sec = _TOC_SEC.search(title)
        entries.append({
            "제목": re.sub(r"\s{2,}", " ", title),
            "쪽": pg,
            "장": cur_ch,
            "절": int(sec.group(1)) if sec else None,
        })
    return entries if len(entries) >= TOC_MIN_LINES else []


def split_table_lines(page: dict) -> list[str]:
    """부록은 표다. 문장으로 나눌 수 없다.

    2013년 부록 83쪽에서 문장이 1개만 나왔다 — 표는 '…하였다.' 로 끝나지
    않기 때문이다. 그렇다고 버리면 수교일·공관 현황·조약 목록 같은
    자료를 통째로 잃는다. **줄 하나를 한 레코드로** 삼는다."""
    out = []
    for line in page["text"].splitlines():
        s = re.sub(r"\s{2,}", " ", line).strip()
        if len(s) < MIN_TABLE_CHARS:
            continue
        if re.fullmatch(r"[\d\s.,·\-—()]+", s):   # 숫자만 있는 줄
            continue
        out.append(s)
    return out


def split_sentences(page: dict) -> list[str]:
    """쪽을 **문장** 단위로 나눈다.

    문단으로 나누려 했으나 이 문서들에는 문단 경계가 기록돼 있지 않다.
    두 가지를 시험하고 둘 다 버렸다(2026-08-15 실측, 2013년 446쪽 기준).

        빈 줄로 나누기   추출본은 줄마다 빈 줄이 들어간다 → 4,615개 중 98%가
                        100자 미만. 한 문장이 세 조각으로 잘렸다
        PDF 블록        이 PDF 는 블록도 줄 단위다 → 4,550개 중 99%가 100자 미만

    문장은 다르다. 한국어 공문서는 '…하였다.' 로 규칙적으로 끝나므로 경계가
    분명하다. 그리고 분석·지식그래프에는 문장이 오히려 낫다 —
    **한 문장이 한 주장**이고, 「정책명」·영문병기·날짜가 문장 단위로 묶인다.
    """
    return [s for _, s in split_sentences_with_pos(
        re.sub(r"\s*\n\s*", " ", page["text"]))]


def split_sentences_with_pos(text: str) -> list[tuple[int, str]]:
    """(시작 글자위치, 문장) 목록. 위치를 함께 주는 이유는 그 문장이 어느
    쪽에서 시작했는지 되짚기 위해서다."""
    out = []
    pos = 0
    for piece in _SENT_END.split(text):
        piece = piece or ""
        s = piece.strip()
        start = pos + (len(piece) - len(piece.lstrip()))
        pos += len(piece) + 1        # split 이 먹은 공백 한 칸
        if len(s) < MIN_PARA_CHARS:
            continue
        if _TOC_LINE.search(s):      # 목차 줄
            continue
        out.append((start, re.sub(r"[ \t]{2,}", " ", s)))
    return out


def trace_structure(text: str, cur: dict) -> dict:
    """본문에서 '제N장'·'제N절'을 만나면 현재 위치를 갱신한다.
    한 쪽 안에서 절이 바뀌면 그 쪽의 뒷부분은 새 절로 본다 — 여기서는
    쪽 단위로만 갱신하므로 경계가 한 쪽 어긋날 수 있다(검사에서 본다)."""
    m = _MARK_CHAPTER.search(text)
    if m:
        cur = {**cur, "chapter": int(m.group(1)), "chapterTitle": m.group(2).strip() or None,
               "section": None, "sectionTitle": None}
    m = _MARK_SECTION.search(text)
    if m:
        cur = {**cur, "section": int(m.group(1)), "sectionTitle": m.group(2).strip() or None}
    return cur


def run_year(year: int, out_root: Path, force: bool) -> dict:
    folder = DATA_ROOT / str(year)
    if not folder.exists():
        raise SystemExit(f"[ERROR] data/{year} 가 없다.")

    out_dir = out_root / str(year)
    if out_dir.exists():
        if not force:
            raise SystemExit(f"[ERROR] {out_dir} 가 이미 있다. --force 로 덮어쓴다.")
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    picked = select_files(year)
    admin = administration(year)
    print(f"{year}년 · {admin} · 파일 {len(picked)}개")

    page_rows: list[dict] = []
    para_rows: list[dict] = []
    toc_rows: list[dict] = []
    sources: list[dict] = []
    seq = 0

    for path, role, chapter in picked:
        pages, err = read_any(path)
        if err:
            print(f"   [실패] {path.name} — {err[:70]}")
            sources.append({"file": path.name, "role": role, "chapter": chapter,
                            "status": "failed", "error": err, "pages": 0})
            continue

        pages, head_stats = strip_pages(pages)
        # 파일명이 알려준 장 번호를 출발점으로 삼는다. 본문에서 갱신된다.
        cur = {"chapter": chapter, "chapterTitle": None, "section": None, "sectionTitle": None}

        # 쪽별 기록은 그대로 남긴다. 원문 확인용이다.
        marks = []          # (글자위치, 쪽정보) — 문장이 어느 쪽에서 시작했는지 되짚는다
        buf = []
        cursor = 0
        n_table = n_toc = 0

        for p in pages:
            cur = trace_structure(p["text"], cur)
            toc = parse_toc(p, chapter)
            kind = "toc" if toc else ("table" if role == "appendix" else "body")
            page_rows.append({
                "연도": year, "정권": admin, "출처파일": path.name, "역할": role,
                "쪽종류": kind,
                "쪽": p["page"], "반쪽": p["half"], "인쇄쪽": p.get("printedPage"),
                "장": cur["chapter"], "절": cur["section"],
                "OCR유래": bool(p.get("ocr")), "원문": p["text"],
            })

            if toc:
                # 목차는 본문이 아니다. 구조 검증용으로 따로 모은다.
                for e in toc:
                    toc_rows.append({**e, "연도": year, "출처파일": path.name, "쪽위치": p["page"]})
                n_toc += len(toc)
                continue

            if role == "appendix":
                # 부록은 표다. 문장으로 못 나누므로 줄 단위로 뽑는다.
                for line in split_table_lines(p):
                    seq += 1
                    para_rows.append({
                        "id": f"{year}-t{seq:05d}", "단위": "표줄",
                        "연도": year, "정권": admin,
                        "장": None, "장제목": None, "절": None, "절제목": None,
                        "쪽": p["page"], "인쇄쪽": p.get("printedPage"),
                        "원문": line,
                        "출처파일": path.name, "역할": role,
                        "OCR유래": bool(p.get("ocr")),
                    })
                    n_table += 1
                continue

            flat = re.sub(r"\s*\n\s*", " ", p["text"]).strip() + " "
            marks.append((cursor, {**cur, "page": p["page"],
                                   "printed": p.get("printedPage"), "ocr": bool(p.get("ocr"))}))
            buf.append(flat)
            cursor += len(flat)

        # **파일 전체를 이어붙여 문장을 나눈다.** 쪽 단위로 자르면 쪽을 넘어가는
        # 문장이 중간에서 끊긴다(2026-08-15 실측: '…이룩함' 처럼 잘렸다).
        whole = "".join(buf)
        n_para = 0
        for start, sent in split_sentences_with_pos(whole):
            info = marks[0][1] if marks else {"chapter": chapter, "chapterTitle": None,
                                              "section": None, "sectionTitle": None,
                                              "page": 1, "printed": None, "ocr": False}
            for pos, m in marks:
                if pos <= start:
                    info = m
                else:
                    break
            seq += 1
            para_rows.append({
                "id": f"{year}-s{seq:05d}", "단위": "문장",
                "연도": year, "정권": admin,
                "장": info["chapter"], "장제목": info["chapterTitle"],
                "절": info["section"], "절제목": info["sectionTitle"],
                "쪽": info["page"], "인쇄쪽": info["printed"],
                "원문": sent,
                "출처파일": path.name, "역할": role,
                "OCR유래": info["ocr"],
            })
            n_para += 1

        sources.append({
            "file": path.name, "role": role, "chapter": chapter, "status": "ok",
            "format": path.suffix.lower().lstrip("."),
            "pages": len(pages), "sentences": n_para, "tableLines": n_table, "tocEntries": n_toc,
            "spread": any(p["half"] for p in pages),
            "ocr": any(p.get("ocr") for p in pages),
            "runningHeads": head_stats,
        })
        extra = (f" {n_table:>4}표줄" if n_table else "") + (f" {n_toc:>4}목차" if n_toc else "")
        print(f"   {path.name[:44]:<46} {len(pages):>4}쪽 {n_para:>5}문장{extra}")

    def dump(name: str, rows: list[dict]) -> None:
        with open(out_dir / name, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    dump("pages.jsonl", page_rows)
    dump("toc.jsonl", toc_rows)
    dump("sentences.jsonl", para_rows)

    # 기준선 — 다시 뽑았을 때 얼마나 달라졌는지 재는 자
    chars = [len(r["원문"]) for r in page_rows]
    meta = {
        "year": year, "administration": admin, "etlVersion": ETL_VERSION,
        "files": {"total": len(picked), "ok": sum(1 for s in sources if s["status"] == "ok"),
                  "failed": sum(1 for s in sources if s["status"] == "failed")},
        "counts": {"pages": len(page_rows), "sentences": len(para_rows),
                   "tocEntries": len(toc_rows), "chars": sum(chars)},
        "baseline": {
            "charsPerPageAvg": round(sum(chars) / len(chars), 1) if chars else 0,
            "emptyPages": sum(1 for c in chars if c < 50),
            "chapters": sorted({r["장"] for r in page_rows if r["장"]}),
        },
        "sources": sources,
    }
    write_json_atomic(out_dir / "meta.json", meta)

    print(f"   → {len(page_rows)}쪽 / {len(para_rows)}문장 / {sum(chars):,}자")
    return meta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, action="append", required=True,
                    help="대상 연도. 여러 번 쓸 수 있다")
    ap.add_argument("--out", default="etl_test", help="산출물 뿌리 폴더")
    ap.add_argument("--force", action="store_true", help="있으면 지우고 다시")
    a = ap.parse_args()

    out_root = PROJECT_ROOT / a.out
    print(f"etl {ETL_VERSION} → {out_root}\n")
    for y in a.year:
        run_year(y, out_root, a.force)
        print()


if __name__ == "__main__":
    main()
