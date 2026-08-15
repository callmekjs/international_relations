"""반복 머리글·꼬리글·쪽번호 제거.

백서는 쪽마다 장·절 제목을 반복해 찍는다. 텍스트로 뽑으면 그 조각이 본문
문장 한가운데로 끼어들어, 인쇄된 문구를 원문 그대로 인용할 수 없게 만든다.

    인쇄된 것 : ②국제협력 증진 및 국가이미지 제고
    뽑은 것   : ②국제협력  국제  증진 및 국가이미지 제고
                          └ 머리글 「2007년 국제 정세 및 외교정책 기조」의 조각

가르는 기준은 **반복**이다. 머리글은 여러 쪽에 똑같이 나오고 본문 문장은
그렇지 않다. 그래서 세어보면 갈린다 — 무엇이 제목인지 알 필요가 없다.

원본(data/)은 건드리지 않는다. 뽑아낸 텍스트만 정리한다.
"""

import re
from collections import Counter

# 머리글로 볼 조건. 느슨하면 본문이 깎이고, 빡빡하면 머리글이 남는다.
MIN_PAGES = 3            # 최소 이만큼의 쪽에 나와야 한다
MIN_RATIO = 0.25         # 그리고 전체 쪽의 이만큼 이상
MAX_HEAD_LEN = 60        # 긴 줄은 본문이다

_PAGE_NUM = re.compile(r"^\s*[\[(]?\s*\d{1,4}\s*[\])]?\s*$")
_WS = re.compile(r"\s+")

# 머리글 앞뒤에 쪽번호가 붙어 나오는 판이 있다(2022~2024).
#   008 제1장 2022년 국제정세 및 외교정책 기조
# 숫자가 매쪽 달라 '반복되는 줄'로 안 잡히고, 그래서 머리글도 안 지워지고
# 쪽번호도 못 건진다. 비교 전에 앞뒤 숫자를 떼어내는 방법을 시험했다가 물렸다
# (2026-08-15): 본문 줄에서도 숫자가 떨어져 나가 서로 다른 문장이 같은 줄로
# 묶였고, 쪽번호는 오히려 줄었으며(2020년 352→175) 2012·2018년 인용문이
# 깨졌다. verify 가 잡아 되돌렸다.
#
# 이 판들의 쪽수는 사람이 인쇄본을 보고 적는다. 머리글 몇 개 지우자고
# 본문을 잃을 수는 없다.


def _key(line: str) -> str:
    """쪽마다 자간·공백이 조금씩 달라 그대로 비교하면 안 잡힌다."""
    return _WS.sub("", line)


def find_running_heads(pages: list[dict]) -> set[str]:
    """여러 쪽에 반복되는 짧은 줄을 찾는다. 반환은 정규화된 키의 집합."""
    n = len(pages)
    if n < MIN_PAGES:
        return set()

    seen_in: Counter[str] = Counter()
    for p in pages:
        keys = set()
        for line in p["text"].splitlines():
            k = _key(line)
            if k and len(k) <= MAX_HEAD_LEN:
                keys.add(k)
        seen_in.update(keys)

    threshold = max(MIN_PAGES, int(n * MIN_RATIO))
    return {k for k, c in seen_in.items() if c >= threshold}


def strip_pages(pages: list[dict]) -> tuple[list[dict], dict]:
    """반복 줄과 쪽번호를 걷어낸다. (정리된 쪽들, 통계) 반환.

    지우기 전에 **인쇄된 쪽번호를 기록해 둔다.** 연구자가 인용할 때 필요한 것은
    PDF 의 몇 번째 장이 아니라 책에 찍힌 쪽수다. 그냥 지우면 그 정보가 사라진다.
    """
    heads = find_running_heads(pages)
    removed_head = removed_num = 0

    out: list[dict] = []
    for p in pages:
        kept: list[str] = []
        printed: list[int] = []
        for line in p["text"].splitlines():
            k = _key(line)
            if not k:
                kept.append(line)
                continue
            if k in heads:
                removed_head += 1
                continue
            if _PAGE_NUM.match(line):
                removed_num += 1
                n = int(_WS.sub("", line).strip("[]()"))
                if 1 <= n <= 2000:      # 연도·전화번호 같은 숫자를 쪽수로 오인하지 않게
                    printed.append(n)
                continue
            kept.append(line)
        # 한 쪽에 숫자 줄이 여럿이면 가장 작은 것을 쪽번호로 본다
        # (본문 중간의 목록 번호보다 쪽번호가 대개 작지는 않지만, 여럿일 때
        #  머리글·꼬리글 자리의 것이 쪽수일 가능성이 높아 최빈값 대신 첫 값을 쓴다)
        out.append({**p, "text": "\n".join(kept),
                    "printedPage": printed[0] if printed else None})

    return out, {
        "runningHeads": len(heads),
        "linesRemovedHead": removed_head,
        "linesRemovedPageNum": removed_num,
        "samples": sorted(heads, key=len, reverse=True)[:8],
    }
