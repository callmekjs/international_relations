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
import hashlib
import io
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from dehead import strip_pages          # noqa: E402
from formats import read_any            # noqa: E402
from hanja_ko import to_hangul          # noqa: E402
from stage_io import PROJECT_ROOT, write_json_atomic  # noqa: E402

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DATA_ROOT = PROJECT_ROOT / "data"
READABLE = {".pdf", ".hwp", ".doc"}

# 원본이 없어서 못 뽑은 것. 사람이 확인해 적어 둔 표다.
# 이것을 산출물에 함께 실어야 "왜 이 해만 적지?"에 답할 수 있다 —
# 자료가 없는 것과 그 해에 일이 없었던 것은 전혀 다르다.
GAPS_TSV = PROJECT_ROOT / "config" / "자료결손.tsv"


def known_gaps(year: int) -> list[dict]:
    if not GAPS_TSV.exists():
        return []
    out, header = [], None
    for line in GAPS_TSV.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cols = line.split("	")
        if header is None:
            header = cols
            continue
        row = dict(zip(header, cols + [""] * (len(header) - len(cols))))
        if row.get("year", "").strip() == str(year):
            out.append({k: v.strip() for k, v in row.items() if k != "year"})
    return out

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
#
# **한글과 한자를 함께 받는다.** 1989~1992년 백서는 국한문 혼용이라 제목이
# `第1章`·`第1節` 로 적혀 있다(네 해에 451줄). 한글만 찾던 탓에 그 네 해의
# 목차가 통째로 비어 있었다(2026-08-16 실측).
#
# 앞에 붙는 장식(`⊙`, `|`)도 넘긴다 — 2009년 목차가 `⊙ 제1절 …` 이다.
_ORNAMENT = r"[\s⊙◦●○▪■·ㅣ|｜─\-_]*"
_MARK_CHAPTER = re.compile(_ORNAMENT + r"(?:제|第)\s*(\d{1,2})\s*(?:장|章)\s*([^\n]{0,60})")
_MARK_SECTION = re.compile(_ORNAMENT + r"(?:제|第)\s*(\d{1,2})\s*(?:절|節|勵)\s*([^\n]{0,60})")

# 문단으로 인정할 최소 길이. 이보다 짧으면 제목·쪽번호 잔해일 가능성이 높다.
MIN_PARA_CHARS = 25   # 문장 단위라 문단보다 짧다

# 이보다 긴 덩어리는 문장이 아니다. 단일 파일 연도는 부록이 파일명으로
# 구별되지 않아 표가 통째로 한 문장이 된다(2020년 46,928자 실측).
# 길이로 알아채고 줄 단위로 되돌린다.
MAX_SENT_CHARS = 1000


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


def select_files(year: int) -> tuple[list[tuple[Path, str, int | None]], list[dict]]:
    """그 해의 **모든** 읽을 수 있는 파일. 부록도 포함한다 — 전문을 뽑는 것이다.

    같은 파일이 이름만 다르게 두 번 들어 있으면 하나만 쓴다. 2004년이
    그랬다(2026-08-16): '2005 외교백서 제1장.pdf' 와 '제2장.pdf' 의 지문이
    똑같았다 — 같은 파일을 복사해 이름만 바꿔 배포한 것이다. 그대로 두면
    1장 내용이 1장으로 한 번, 2장으로 또 한 번 세어져 통계가 부풀려진다.

    **원본은 건드리지 않는다.** 배포된 자료를 우리가 지울 일이 아니고,
    거르는 일은 파이프라인이 할 몫이다."""
    folder = DATA_ROOT / str(year)
    picked, seen, skipped = [], {}, []
    for f in sorted(folder.iterdir()):
        if not (f.is_file() and f.suffix.lower() in READABLE):
            continue
        digest = hashlib.sha256(f.read_bytes()).hexdigest()
        if digest in seen:
            print(f"   ! {f.name} 은 {seen[digest]} 와 같은 파일 — 건너뛴다")
            skipped.append({"file": f.name, "sameAs": seen[digest], "reason": "중복"})
            continue
        seen[digest] = f.name
        role, ch = classify(f.stem)
        picked.append((f, role, ch))
    picked.sort(key=lambda t: sort_key(t[1], t[2]))
    return picked, skipped


# 한국어 공문서의 문장 끝. 이 형태들로 끝나고 뒤에 공백이 오면 문장이 끊긴다.
_SENT_END = re.compile(r"(?<=다\.)\s|(?<=다\.\”)\s|(?<=음\.)\s|(?<=임\.)\s|(?<=함\.)\s")

# 목차·표 잔해를 걸러낸다. 점선이 길게 이어지거나 숫자만 있는 줄이다.
_TOC_LINE = re.compile(r"[.·…]{5,}|^\s*[\d\s.·]+$")

# 목차 한 줄:  제목 …… 쪽번호
#
# 앞서 `(.{4,60}?)\s*[.·…\s]{2,}\s*` 로 썼다가 물렸다(2026-08-15).
# 가운데 `\s` 가 앞뒤 `\s*` 와 겹쳐서, 안 맞는 긴 줄을 만나면 경우의 수가
# 폭발해 10분을 넘겨도 안 끝났다. 점선 문자만 요구해 겹침을 없앤다.
#
# 판마다 목차 모양이 다르다. 셋 다 받아야 한다(2026-08-15 실측).
#   ① 제목……045      2013년
#   ② 제목    045     2020·2002년 (점선 없이 공백만)
#   ③ 008  제목       2020년 (쪽번호가 앞)
# 이걸 놓치면 목차 쪽이 본문으로 처리돼 목차의 절 번호가 본문 절을 덮어쓴다.
# 2020년 절 결측 45%의 진짜 원인이었다.
_TOC_ENTRY = re.compile(r"^\s*(\S[^\n]{2,58}?)[.·…]{2,}\s*(\d{1,3})\s*$")
# 공백형은 위험하다. 본문 문장도 '…하였다.   17' 처럼 끝나면 목차로 오인된다.
# 실제로 2002년 정답지가 6/6 → 3/6 으로 떨어졌다(2026-08-15). 그래서 제목이
# **장·절 표시로 시작할 때만** 인정한다.
_TOC_ENTRY_SPACED = re.compile(r"^\s*(제\s*\d{1,2}\s*[장절][^\n]{2,54}?)\s{2,}(\d{1,3})\s*$")
_TOC_ENTRY_NUMFIRST = re.compile(r"^\s*(\d{1,3})\s{2,}(제\s*\d{1,2}\s*[장절][^\n]{0,54})\s*$")
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

        title = pg = None
        m = _TOC_ENTRY.match(line) or _TOC_ENTRY_SPACED.match(line)
        if m:
            title, pg = m.group(1).strip(), int(m.group(2))
        else:
            m = _TOC_ENTRY_NUMFIRST.match(line)
            if m:
                pg, title = int(m.group(1)), m.group(2).strip()
        if not title or pg is None or pg > 2000:
            continue
        # 숫자만 있거나 너무 짧은 제목은 목차가 아니다
        if len(re.sub(r"[\d\s.·…|]", "", title)) < 3:
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


# 장·절 제목으로 인정할 줄의 최대 길이. 제목은 짧다. 본문 문장 속의
# '제2장 참조' 같은 언급과 가르는 기준이다.
HEADING_MAX_LINE = 50


# 제목이 다음 줄에 있을 때, 그 줄이 제목일 수 있는 최대 길이.
# 제목은 짧다. 이보다 길면 제목이 아니라 본문이 이어진 것이다.
TITLE_NEXTLINE_MAX = 42
# 문장으로 끝나면 제목이 아니다. 제목에는 마침표를 찍지 않는다.
_TITLE_NOT_END = re.compile(r"(다|음|임|함)\s*[.]\s*$|[.?!]\s*$")

_PATS = {"장": _MARK_CHAPTER, "절": _MARK_SECTION}


def _looks_like_title(s: str) -> bool:
    """다음 줄을 제목으로 데려올 수 있는가."""
    s = s.strip()
    if not s or len(s) > TITLE_NEXTLINE_MAX:
        return False
    if _TITLE_NOT_END.search(s):
        return False
    # 다음 줄이 또 장·절 표시면 앞 표시는 제목이 없는 것이다
    if _MARK_CHAPTER.match(s) or _MARK_SECTION.match(s):
        return False
    return bool(re.search(r"[가-힣一-鿿]", s))


def read_heading(lines: list[str], i: int, kind: str) -> tuple[int, str | None] | None:
    """`lines[i]` 가 **제목 줄 자체**인가. 맞으면 (번호, 제목).

    본문에 '제2장' 이라는 말이 나온 것과 다르다 — 줄 **머리**에 있어야 한다.

    **제목이 다음 줄에 있는 판이 많다.** 2003년과 2009~2025년에 걸쳐 507줄이
    이 모양이다(2026-08-16 실측).

        제1절            ← 이 줄
        국제 정세 개관    ← 제목은 여기

    한 줄만 보던 탓에 제목을 못 찾았을 뿐 아니라, 앞서 잡아둔 제목까지
    `없음`으로 덮어썼다. 그래서 2009~2012년은 절 번호는 98% 붙어 있는데
    절 제목은 0% 라는 모양이 나왔다."""
    s = lines[i].strip()
    if not s or len(s) > HEADING_MAX_LINE:
        return None
    m = _PATS[kind].match(s)          # 줄 **머리**에 있어야 한다
    if not m:
        return None
    title = _clean_title(m.group(2))
    if title is None:
        for nxt in lines[i + 1:i + 3]:      # 빈 줄 하나까지는 건너뛴다
            if not nxt.strip():
                continue
            if _looks_like_title(nxt):
                title = _clean_title(nxt)
            break
    return int(m.group(1)), title


def hard_split(blob: str) -> list[str]:
    """긴 덩어리를 **무슨 일이 있어도** 조각낸다.

    앞서 공백 3칸으로만 끊었더니, 그 기준이 안 통하는 덩어리는 이름만
    '표줄'로 바뀐 채 46,928자 그대로 남았다(2026-08-15 실측). 레코드 하나가
    전체 글자의 6%를 차지해 통계를 망가뜨린다.

    끊는 자를 여러 개 두고, 그래도 길면 마지막에는 길이로 자른다."""
    pieces = [blob]
    for sep in (r"\s{3,}", r"\n", r"(?<=\d\.)\s", r"(?<=\))\s", r"(?<=\d\))\s"):
        nxt = []
        for x in pieces:
            nxt.extend(re.split(sep, x) if len(x) > MAX_SENT_CHARS else [x])
        pieces = nxt

    out = []
    for x in pieces:
        x = re.sub(r"\s{2,}", " ", x).strip()
        while len(x) > MAX_SENT_CHARS:      # 끝내 안 끊기면 길이로 자른다
            out.append(x[:MAX_SENT_CHARS])
            x = x[MAX_SENT_CHARS:]
        if len(x) >= MIN_TABLE_CHARS and not re.fullmatch(r"[\d\s.,·\-—()]+", x):
            out.append(x)
    return out


def trace_line(lines: list[str], i: int, cur: dict, lock_chapter: bool) -> dict:
    """`lines[i]` 를 보고 장·절을 갱신한다. 제목 줄일 때만 바뀐다.

    줄 하나가 아니라 **줄 목록과 자리**를 받는 이유는, 제목이 다음 줄에
    있는 판이 있기 때문이다(`read_heading` 참고)."""
    if not lock_chapter:
        h = read_heading(lines, i, "장")
        if h:
            # **같은 장이면 절을 건드리지 않는다.** 쪽마다 반복되는 머리글
            # ('제1장 2020년 국제 정세 및 외교정책 기조')이 매번 절을 지워서
            # 2020년 절 결측이 45%였다. 장이 실제로 바뀔 때만 절을 초기화한다.
            if h[0] == cur.get("chapter"):
                return cur
            return {**cur, "chapter": h[0], "chapterTitle": h[1],
                    "section": None, "sectionTitle": None}
    h = read_heading(lines, i, "절")
    if h:
        # **제목을 못 읽었다고 앞서 잡은 제목을 지우지 않는다.**
        # 같은 절이면 그대로 두고, 절이 바뀌었으면 번호만 새로 쓴다.
        # 이 한 줄이 2009~2012년 절 제목 결측 100% 의 원인이었다.
        if h[1] is None and h[0] == cur.get("section"):
            return cur
        return {**cur, "section": h[0],
                "sectionTitle": h[1] if h[1] is not None else None}
    return cur


# 제목 앞뒤에 붙는 것들. 판마다 다르고, 스캔본은 OCR 이 장식을 더 만든다.
#   '| 국제 정세 개관'          2019년 쪽 머리글 기호
#   '_2025년 국제정세…'         2025년 (장 번호와 제목을 밑줄로 이음)
#   '。 東北亞 및 韓半島 情勢'    1990년 (한자판 장식점)
#   '”世界의 主要情勢'           1990년 (OCR 이 만든 따옴표)
_TITLE_HEAD = re.compile(r'^[|｜:：\-—_\s。、·．.”"\'`]+')
#   '신아시아 협력외교·54'       2009년 (쪽번호를 · 로 붙임)
#   '국제협력 및 연대 추진   045' 2020년
#   '國際機構 活動 07'           1990년
_TITLE_TAIL = re.compile(r"[\s.·…‥]*\d{1,4}\s*$")
# OCR 이 점선을 글자로 잘못 읽은 꼬리. '協力eeaeeeeasaes..。 27' 같은 것.
_TITLE_OCR_TAIL = re.compile(r"[a-zA-Z]{4,}[^가-힣一-鿿]*$")


# 제목 안에 또 다른 장·절 표시가 올 수 없다. 나오면 거기서 자른다.
# 스캔본은 쪽 머리글을 지우면서 두 제목이 한 줄로 붙는 일이 있다
#   '제1절 국제 정세 개관 / 제2절 외교정책 기조 및 추진 경과 _'   (2017년)
_TITLE_CUT = re.compile(r"[\s/|｜]*(?:제|第)\s*\d{1,2}\s*(?:장|절|章|節)")
# 스캔본 꼬리. '_ 6?', '_', '?' 같은 것들이 붙는다.
_TITLE_SCAN_TAIL = re.compile(r"[\s_~^]*\d{0,4}\s*[?？]?\s*$")


def _clean_title(t: str) -> str | None:
    """제목 앞뒤에 붙은 장식·쪽번호를 떼어낸다."""
    t = _TITLE_HEAD.sub("", t or "")
    cut = _TITLE_CUT.search(t)
    if cut:
        t = t[:cut.start()]
    t = _TITLE_SCAN_TAIL.sub("", t)
    t = _TITLE_TAIL.sub("", t)
    t = _TITLE_OCR_TAIL.sub("", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" .·…‥、,")
    # 글자가 하나도 안 남으면 제목이 아니다
    if not re.search(r"[가-힣一-鿿A-Za-z]", t):
        return None
    return t or None


def trace_structure(text: str, cur: dict, lock_chapter: bool) -> dict:
    """쪽을 훑어 현재 장·절을 갱신한다.

    2026-08-15 실측: 본문에 '제2장' 이라는 **말이 나오기만 하면** 장을 바꾸던
    탓에, 2013년 제1장 파일에서 나온 172문장 중 장=1 인 것이 16개뿐이었다.
    나머지는 엉뚱한 장으로 갔다.

    그래서 두 가지를 바꿨다.
      1) 파일명이 장을 알려준 파일(제1장.pdf)에서는 **본문이 장을 못 바꾼다.**
         파일명이 본문보다 믿을 만하다.
      2) 단일 파일이라 파일명이 안 알려줄 때만 본문에서 찾되, 그 줄이
         **제목 줄 자체**일 때만 인정한다(짧고, 줄 머리에 있어야 한다).
    """
    lines = text.splitlines()
    for i in range(len(lines)):
        cur = trace_line(lines, i, cur, lock_chapter)
    return cur


def run_year(year: int, out_root: Path, force: bool) -> dict:
    folder = DATA_ROOT / str(year)
    if not folder.exists():
        raise SystemExit(f"[ERROR] data/{year} 가 없다.")

    out_dir = out_root / str(year)
    # '끝났다'의 기준은 폴더가 아니라 meta.json 이다. 폴더는 그 해를 **시작할 때**
    # 만들어지므로, 도중에 멈추면 빈 껍데기가 남는다. 그것을 '이미 있다'로 보면
    # 다음 실행이 거기서 멈춘다 — 2026-08-16 새벽에 빈 1990 폴더 하나가 밤샘
    # 작업을 5시간 반 동안 세웠다.
    if (out_dir / "meta.json").exists():
        if not force:
            raise SystemExit(f"[ERROR] {out_dir} 는 이미 끝났다. --force 로 덮어쓴다.")
        shutil.rmtree(out_dir)
    elif out_dir.exists():
        shutil.rmtree(out_dir)      # 하다 만 흔적 — 조용히 치우고 다시 한다
    out_dir.mkdir(parents=True)

    picked, skipped = select_files(year)
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
            cur = trace_structure(p["text"], cur, lock_chapter=(chapter is not None))
            toc = parse_toc(p, chapter)
            kind = "toc" if toc else ("table" if role == "appendix" else "body")
            page_rows.append({
                "연도": year, "정권": admin, "출처파일": path.name, "역할": role,
                "쪽종류": kind,
                "쪽": p["page"], "반쪽": p["half"], "인쇄쪽": p.get("printedPage"),
                "장": cur["chapter"], "절": cur["section"],
                "OCR유래": bool(p.get("ocr")), "원문": p["text"],
                "한글": to_hangul(p["text"])[0],
            })

            if toc:
                # 목차는 본문이 아니다. 구조 검증용으로 따로 모은다.
                for e in toc:
                    toc_rows.append({**e, "연도": year, "출처파일": path.name, "쪽위치": p["page"]})
                n_toc += len(toc)
                # **쪽을 통째로 버리지 않는다.** HWP·DOC 는 파일 하나가 '1쪽'
                # 이라, 그 쪽을 목차로 판정하면 파일 전체가 사라진다.
                # 2002년 정답지가 6/6 → 3/6 으로 떨어진 원인이었다.
                # 목차로 잡힌 줄만 빼고 나머지는 그대로 본문으로 다룬다.
                toc_lines = {re.sub(r"\s+", "", e["제목"]) for e in toc}
                kept = [ln for ln in p["text"].splitlines()
                        if re.sub(r"\s+", "", ln)[:40] not in
                        {t[:40] for t in toc_lines} and not _TOC_LINE.search(ln)]
                p = {**p, "text": "\n".join(kept)}
                if len(p["text"].strip()) < 200:
                    continue        # 진짜 목차 전용 쪽이면 남는 게 없다

            if role == "appendix":
                # 부록은 표다. 문장으로 못 나누므로 줄 단위로 뽑는다.
                for line in split_table_lines(p):
                    seq += 1
                    para_rows.append({
                        "id": f"{year}-t{seq:05d}", "단위": "표줄",
                        "연도": year, "정권": admin,
                        "장": None, "장제목": None, "절": None, "절제목": None,
                        "쪽": p["page"], "인쇄쪽": p.get("printedPage"),
                        "원문": line, "한글": to_hangul(line)[0],
                        "출처파일": path.name, "역할": role,
                        "OCR유래": bool(p.get("ocr")),
                    })
                    n_table += 1
                continue

            # 장·절을 **줄 단위로** 따라간다. 쪽 단위로 하면 두 가지가 깨진다.
            #   1) 한 쪽 안에서 절이 바뀌면 그 쪽 전체가 한쪽 절로 몰린다
            #   2) HWP·DOC 는 파일 하나가 통째로 '1쪽' 이라 파일 전체가 한 값을 받는다
            #      (2002년 절 결측 27.7%, 2020년 45.2% 의 원인이었다)
            page_lines = p["text"].splitlines()
            for li, line in enumerate(page_lines):
                cur = trace_line(page_lines, li, cur, lock_chapter=(chapter is not None))
                piece = line.strip()
                if not piece:
                    continue
                marks.append((cursor, {**cur, "page": p["page"],
                                       "printed": p.get("printedPage"),
                                       "ocr": bool(p.get("ocr"))}))
                buf.append(piece + " ")
                cursor += len(piece) + 1

        # **파일 전체를 이어붙여 문장을 나눈다.** 쪽 단위로 자르면 쪽을 넘어가는
        # 문장이 중간에서 끊긴다(2026-08-15 실측: '…이룩함' 처럼 잘렸다).
        whole = "".join(buf)
        n_para = 0
        for start, sent in split_sentences_with_pos(whole):
            # 너무 긴 것은 문장이 아니라 표다. 단일 파일 연도는 부록이 파일명으로
            # 구별되지 않아 표가 통째로 한 덩어리가 된다(2020년 46,928자 실측).
            if len(sent) > MAX_SENT_CHARS:
                info2 = marks[0][1] if marks else None
                for pos, mm in marks:
                    if pos <= start:
                        info2 = mm
                    else:
                        break
                for line in hard_split(sent):
                    if len(line) < MIN_TABLE_CHARS or re.fullmatch(r"[\d\s.,·\-—()]+", line):
                        continue
                    seq += 1
                    para_rows.append({
                        "id": f"{year}-t{seq:05d}", "단위": "표줄",
                        "연도": year, "정권": admin,
                        "장": info2["chapter"] if info2 else None, "장제목": None,
                        "절": None, "절제목": None,
                        "쪽": info2["page"] if info2 else None,
                        "인쇄쪽": info2["printed"] if info2 else None,
                        "원문": line, "한글": to_hangul(line)[0],
                        "출처파일": path.name, "역할": role,
                        "OCR유래": info2["ocr"] if info2 else False,
                    })
                    n_table += 1
                continue
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
                "원문": sent, "한글": to_hangul(sent)[0],
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
    #
    # 공백을 빼고 센다. 옛 PDF 는 칸을 맞추려고 여백 공백을 잔뜩 넣어 두는데,
    # 그것까지 세면 '내용'이 아니라 '조판'을 재게 된다. 2026-08-16 에 띄어쓰기
    # 되살리기를 넣었더니 2013년 글자수가 437,801 → 303,062 (-31%) 로 떨어져
    # 기준선이 헛경보를 울렸다 — 줄어든 13만 자는 전부 여백 공백이었고
    # 문장 수는 1,767 → 1,769 로 그대로였다.
    chars = [len("".join(r["원문"].split())) for r in page_rows]
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
        "skipped": skipped,
        "knownGaps": known_gaps(year),
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
