"""1989~1997년 백서에서 **그 해의 외교 우선순위**를 뽑아 표 초안을 만든다.

    python scripts/harvest_priorities.py            무엇이 뽑히는지 본다
    python scripts/harvest_priorities.py --tsv      authoring 에 붙일 줄을 찍는다

**왜 필요한가.** 화면(web-demo)은 `authoring/` 의 손으로 적은 표만 읽는다.
그 표가 1998년부터라서 **노태우·김영삼 두 정권 아홉 해가 화면에 아예 없었다.**
정권 교체 비교도 8건 중 6건만 나왔다.

**지어내지 않는다.** 여기서 하는 일은 원문에 이미 적혀 있는 글자를 **그대로
옮기는 것**뿐이다. 옮긴 것이 원문에 정말 있는지는 `verify.py` 가 한 글자씩
대조한다 — 지어내면 그 자리에서 걸린다.

**두 가지 모양이 있다.**

    ① 번호 목록형   1996·1997년
         제 2 절 1997년도 주요 외교시책
           1. 세계화 외교  2. 안보 통일외교  3. 경제 통상외교  4. 재외동포 보호 육성

    ② 한 문장 나열형  1992~1995년   (1998년 표가 쓰는 방식과 같다)
         "…1992년도에 몇가지 외교시책을 중점적으로 추진하였는 바, 그 내용은
          대우방 관계의 발전적 강화, 북방외교의 마무리와 내실화, … 등이었다."

**1989~1991년은 뽑지 않는다.** 스캔 글자 인식이 심하게 깨져 정책 이름이
글자로 남아 있지 않다(`3. 뷰푸 배스` · `\\-흐 빼셰플를 )2푸`).
없는 것을 지어내느니 **'원문 확인 필요' 로 두는 것**이 이 프로젝트의 방식이다.
"""

import argparse
import io
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

TEXT_ROOT = PROJECT_ROOT / "text"

# 뽑을 해. 1989~1991 은 글자가 깨져 뺀다 — 위 설명 참고.
YEARS = range(1992, 1998)

# ① 번호 목록형. 절 제목 바로 뒤에 '1. …' 이 줄줄이 온다.
_SECTION_HEAD = re.compile(r"제\s*\d\s*절\s*_?\s*\d{4}\s*[년넌]도\s*"
                          r"(?:주요\s*외교시책|주요\s*정책\s*목표|주요정책\s*목표|"
                          r"주요\s*외교정책\s*목표)")
# 제목에 붙임표·괄호·숫자가 들어간다. 좁게 잡으면 거기서 목록이 끊긴다 —
# 1993년 '3. 능동적인 아-태 외교 전개' 의 붙임표 하나에 세 항목을 잃었다.
_NUM_ITEM = re.compile(
    r"^\s*(\d)\s*[.．]?\s*([가-힣][가-힣A-Za-z0-9·ㆍ()\-–—~∼\s]{3,34})\s*$", re.M)

# ② 한 문장 나열형. '그 내용은 A, B, C 등이었다' / 'A, B, C 등을 설정하고'
#
# 줄바꿈은 넘되 **빈 줄(문단 경계)은 넘지 않는다.** 그냥 re.S 로 열어두면
# 앞 문장의 기조와 뒤 문장의 시책이 한 덩어리로 잡힌다 — 1992년이 그랬다
# (기조 2개 + 시책 5개 = 7개로 부풀었다).
_IN_PARA = r"(?:[^\n]|\n(?!\n))"
_LEAD = re.compile(
    r"(?:그\s*내용은|시책으로서|목표로서|목표로|기조로서)\s*"
    rf"({_IN_PARA}{{20,400}}?)\s*"
    r"(?:등이었다|등을\s*설정|등으로\s*정하고|등에\s*주안점|등\s*\d가지를\s*설정)")
# 나열을 가르는 자리. '그리고' 는 마지막 항목 앞에 붙는다.
_SPLIT = re.compile(r"\s*(?:,|、|그리고)\s*")
# 원문이 항목마다 따옴표를 두른 판이 있다(1995·1996년).
#   "세계화 외교', '안보ㆍ통일 외교', 、경제ㆍ통상 외교', '재외동포정책'
# 그때는 쉼표로 자르는 것보다 따옴표 안을 그대로 쓰는 편이 깨끗하다.
# 스캔본이라 여는 따옴표가 제각각(“ ' 、 『)이므로 넉넉히 받는다.
_QUOTEMARK = re.compile(r"[\"'“”‘’、『』「」]+\s*,?\s*"
                        r"|\s*,\s*(?=[\"'“”‘’、『「])")
# 항목이 아니라 이어주는 말인 조각. 접속어만 남은 것을 뺀다.
_JUNK = re.compile(r"^(및|등|그리고|또한|이의|이를|한편)|^[^가-힣]*$")

# 우선순위를 어느 줄기에 넣을까. streams.tsv 의 id 를 쓴다.
# 열쇠말은 전부 뽑힌 제목에 실제로 나온 말이다.
STREAMS = [
    ("peninsula", ["통일", "한반도", "북한", "북방", "평화정착", "안보체제", "안보"]),
    ("neighbors", ["대우방", "우방", "미국", "일본", "중국", "러시아", "주변"]),
    ("economy", ["경제", "통상", "실리"]),
    ("global-role", ["유엔", "국제협력", "다자", "국제기구", "국제사회"]),
    ("overseas-koreans", ["재외동포", "재외국민", "교포", "영사"]),
    ("public-diplomacy", ["문화", "공보", "홍보", "국가이미지"]),
    ("regional", ["아-태", "아태", "지역", "다변화", "세계화"]),
    ("capacity", ["역량", "조직", "인사", "체제 정비", "외교수행체제", "경쟁력"]),
    # 아래는 위 어디에도 안 걸린 제목을 보고 더한 것이다(2026-08-16).
    #   '아ㆍ뿌 협력심화'(아ㆍ태의 OCR 오독) · '정상외교 추진' · '재외한인지원'
    #   '국제화 시대에 부응한 국가위상 제고'
    ("regional", ["아ㆍ뿌", "아·뿌", "아뿌"]),
    ("neighbors", ["정상외교"]),
    ("overseas-koreans", ["재외한인", "한인지원"]),
    ("global-role", ["국가위상", "국제화"]),
]


def stream_of(title: str) -> str:
    t = re.sub(r"\s+", "", title)
    for sid, keys in STREAMS:
        if any(re.sub(r"\s+", "", k) in t for k in keys):
            return sid
    return ""


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip(" .,·ㆍ'\"“”‘’")


def numbered(text: str) -> tuple[list[str], str]:
    """① 번호 목록형."""
    m = _SECTION_HEAD.search(text)
    if not m:
        return [], ""
    # 항목 사이에 본문이 끼어 있는 판이 있다(1993년). 창을 넉넉히 준다 —
    # 번호가 1,2,3… 으로 이어질 때만 받으므로 넓혀도 딴것이 섞이지 않는다.
    after = text[m.end(): m.end() + 6000]
    items, want = [], 1
    for mm in _NUM_ITEM.finditer(after):
        n, title = int(mm.group(1)), clean(mm.group(2))
        if n != want:
            break                     # 1,2,3… 이 끊기면 목록이 끝난 것이다
        items.append(title)
        want += 1
    # 인용은 **절 제목과 항목 목록**을 남긴다. 앞 문단을 끌어오면
    # 근거와 상관없는 글이 인용으로 들어간다(1993년이 그랬다).
    last = 0
    for mm in _NUM_ITEM.finditer(after):
        if int(mm.group(1)) > len(items):
            break
        last = mm.end()
    return items, clean(text[m.start(): m.end() + last])


def from_lead(text: str) -> tuple[list[str], str]:
    """② 한 문장 나열형. 인용은 **문장 통째로** 남긴다."""
    best: tuple[list[str], str] = ([], "")
    for m in _LEAD.finditer(text):
        inner = m.group(1)
        # 따옴표로 항목을 두른 판이면 그것을 쓴다. 아니면 쉼표로 자른다.
        #
        # **짝이 안 맞아도 잘라야 한다.** 스캔본은 여는 따옴표를 자주 먹는다
        #   "…“핵 문제 해결과 평화정착 모색”, “새로운 경제환경에 능동적 대처”,
        #    유엔 등 국제기구 외교 강화", "문화외교의 내실화”…"
        # 짝을 요구하면 여기서 두 개를 놓친다. 그래서 따옴표를 **자르는 자리**로만
        # 쓰고, 잘린 조각 중 제목처럼 생긴 것을 남긴다.
        if len(_QUOTEMARK.findall(inner)) >= 4:
            parts = [clean(p) for p in _QUOTEMARK.split(inner)]
        else:
            parts = [clean(p) for p in _SPLIT.split(inner)]
        parts = [p for p in parts if 4 <= len(p) <= 40 and not _JUNK.match(p)]
        if len(parts) < 3:
            continue
        # 인용은 그 문장 전체 — 어디서 왔는지 사람이 되짚을 수 있어야 한다
        s = text.rfind("\n\n", 0, m.start()) + 2
        e = text.find("\n\n", m.end())
        quote = clean(text[s: e if e > 0 else m.end() + 60])
        if len(parts) > len(best[0]):
            best = (parts, quote)
    return best


def harvest(year: int) -> tuple[list[str], str, str]:
    p = TEXT_ROOT / f"{year}.txt"
    if not p.exists():
        return [], "", "원문 파일 없음"
    text = p.read_text(encoding="utf-8")
    # **두 방법을 다 해보고 많이 뽑히는 쪽을 쓴다.** 1996년은 번호 목록이
    # 한 줄만 붙어 있고 나머지는 본문 사이에 흩어져 있어, 목록만 믿으면
    # 1개로 끝난다.
    n_items, n_quote = numbered(text)
    l_items, l_quote = from_lead(text)
    if len(n_items) >= max(len(l_items), 2):
        return n_items, n_quote, "번호목록"
    if len(l_items) >= 2:
        return l_items, l_quote, "시책절"
    return [], "", "못 찾음"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv", action="store_true", help="authoring 에 붙일 줄을 찍는다")
    a = ap.parse_args()

    rows = []
    for y in YEARS:
        items, quote, how = harvest(y)
        if not a.tsv:
            print(f"\n{'='*70}\n{y}년 · {how} · {len(items)}개")
            for i, t in enumerate(items, 1):
                print(f"   {i}. {t:<34} → {stream_of(t) or '(줄기 미정)'}")
            if quote:
                print(f"   인용: {quote[:150]}")
        for i, t in enumerate(items, 1):
            rows.append({
                "id": f"{y}-{i}", "coverageYear": y, "ordinal": i,
                "ordinalSource": "시책절", "title": t, "quote": quote,
                "stream": stream_of(t), "srcEdition": f"{y+1} 외교백서",
                "srcChapter": "", "srcSection": "", "srcPage": "",
                "flags": "lead-only" if how == "시책절" else "",
            })

    if a.tsv:
        cols = ["id", "coverageYear", "ordinal", "ordinalSource", "title", "quote",
                "stream", "srcEdition", "srcChapter", "srcSection", "srcPage", "flags"]
        for r in rows:
            print("\t".join(str(r[c]) for c in cols))
    else:
        print(f"\n{'='*70}\n모두 {len(rows)}줄 · 줄기 못 정한 것 "
              f"{sum(1 for r in rows if not r['stream'])}개")
        print("1989~1991 은 글자가 깨져 뽑지 않는다 — 화면에는 '원문 확인 필요' 로 둔다.")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    main()
