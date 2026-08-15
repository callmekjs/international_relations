"""대조용 정규화 — 스펙 §7.

인용문이 원문에 글자 그대로 있는지 확인할 때, 추출 텍스트와 사람이 친 인용문
**양쪽에 똑같이** 적용한다. 한쪽에만 걸면 검증이 무의미해진다.

여기서 하는 일은 대조에 한정된다. `data.json` 에 실려 화면에 나가는 인용문은
사람이 인쇄본을 보고 친 것 그대로이고 이 함수를 거치지 않는다 — 그래서 PDF
추출이 망가져도 독자가 보는 글자는 멀쩡하다.

스펙 §7 대비 추가된 두 가지 (2026-08-15, 실측 근거):

  1. NFC 정규화 — 호환용 한자(U+F900~FAFF)가 섞여 들어온다. 李 U+F9E1 과
     李 U+674E 는 눈으로 같지만 코드가 달라 문자열 비교가 실패한다.
     실측: 1999·2000·2001·2018 에서 李 4회, 兩 1회.

  2. 공백 전부 제거 — §7 은 "연속 공백을 하나로" 였는데, 2003·2004 추출본은
     공백이 통째로 사라진다("쟝쩌민전국가주석만당및…", 공백률 8.0%).
     줄이는 것으로는 닿지 않아 아예 무시한다. 띄어쓰기는 판본마다 흔들리는
     정보라 잃어도 대조의 엄밀함이 떨어지지 않는다.
"""

import re
import unicodedata
from pathlib import Path

CONFIG = Path(__file__).resolve().parent.parent / "config"
REPAIRS_PATH = CONFIG / "text_repairs.tsv"

# 중점 계열은 판본·폰트마다 다른 코드가 쓰인다. 하나로 모은다.
# U+2024(․, ONE DOT LEADER)는 1999~2002년 HWP 판에서 가운뎃점 자리에 쓰였다
# ('한․미․일'). 눈으로는 · 와 구별되지 않아 옮겨 적을 때 반드시 어긋난다.
_MIDDOT = "·・∙･•‧․﹒．ㆍ"   # ㆍ(U+318D)는 2017·2019 OCR 결과에서 가운뎃점 자리에 나온다
# 따옴표
_SINGLE_Q = "‘’‛′"
_DOUBLE_Q = "“”‟″"
# 폭 없는 문자·소프트하이픈 — 눈에 안 보이는데 비교를 깬다
_INVISIBLE = re.compile(r"[​-‏­﻿⁠]")
_WHITESPACE = re.compile(r"\s+")


def load_repairs(path: Path = REPAIRS_PATH) -> dict[str, str]:
    """교정표를 읽는다. 코드에 박지 않고 파일에 두는 것은, 새 손상이 나올 때마다
    근거와 함께 한 줄 늘리는 자리가 필요하기 때문이다."""
    if not path.exists():
        return {}
    table: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) < 2:
            continue
        table[cols[0]] = cols[1]
    return table


_REPAIRS = load_repairs()


def normalize_for_match(s: str, repairs: dict[str, str] | None = None) -> str:
    """대조용으로 정규화한다. 되돌릴 수 없으니 원문 보관에는 쓰지 않는다."""
    table = _REPAIRS if repairs is None else repairs

    s = unicodedata.normalize("NFC", s)      # 호환용 한자 → 통합 한자
    for wrong, right in table.items():       # 폰트 오추출 되돌리기
        if wrong in s:
            s = s.replace(wrong, right)
    s = _INVISIBLE.sub("", s)
    for ch in _MIDDOT:
        s = s.replace(ch, "·")
    for ch in _SINGLE_Q:
        s = s.replace(ch, "'")
    for ch in _DOUBLE_Q:
        s = s.replace(ch, '"')
    s = _WHITESPACE.sub("", s)               # 공백 전부 제거 (§7 개정)
    return s


# 낫표「」와 괄호 안 영문 병기는 보존한다 — §9 확장축의 채굴 대상이라
# 정규화 단계에서 지우면 나중에 되찾을 수 없다.


def split_ellipsis(quote: str) -> list[str]:
    """인용 안의 (…) 는 생략을 뜻한다. 그 표시로 잘라 조각 목록을 돌려준다.
    각 조각이 원문에 '순서대로' 나타나면 통과다."""
    parts = re.split(r"\(\s*(?:…|\.\.\.|⋯)\s*\)", quote)
    return [p for p in (x.strip() for x in parts) if p]
