"""한자를 한글로 옮긴다. **원문은 절대 건드리지 않는다.**

분석과 지식그래프는 한글 칸을 쓰고, 인용은 원문 칸을 쓴다. 원문을 덮어쓰면
되돌릴 수 없고, 되돌릴 수 없는 변환은 자료를 잃는 것과 같다.

## 괄호 안 한자는 바꾸지 않는다

    1989~1996 본문(국한문 혼용)
        北韓의 對外政策    →  북한의 대외정책        맞다

    2000년대 괄호 병기
        주룽지(朱鎔基)     →  주룽지(주용기)         틀리다
                              앞에 이미 한글이 있고, 원문은 '주룽지'다
                              한자음(주용기)과 실제 표기(주룽지)가 다르다

괄호 안에 한자만 들어 있고 그 앞에 한글이 붙어 있으면 **병기**다. 그대로 둔다.
"""

import re

try:
    import hanja as _hanja
except ImportError:          # 설치 전에도 파이프라인이 죽지 않게
    _hanja = None

HAS_HANJA = _hanja is not None

# 한자 한 글자
_HANJA = r"一-鿿㐀-䶿豈-﫿"
# 한글 바로 뒤에 오는 (한자만 든) 괄호 = 병기. 예: 주룽지(朱鎔基), 아세안(ASEAN)
_GLOSS = re.compile(rf"(?<=[가-힣])\s*[（(][\s{_HANJA}·，,]+[)）]")
_HAS_HANJA = re.compile(rf"[{_HANJA}]")


def to_hangul(text: str) -> tuple[str, int]:
    """(한글로 옮긴 글, 바꾼 글자 수).

    한자가 없으면 원문을 그대로 돌려준다 — 대부분의 해가 여기 해당한다."""
    if not text or not _HAS_HANJA.search(text):
        return text, 0
    if _hanja is None:
        return text, 0

    # 병기 괄호는 자리표시자로 빼두고, 나머지만 옮긴 뒤 되돌린다
    kept: list[str] = []

    def stash(m: re.Match) -> str:
        kept.append(m.group(0))
        return f"\x00{len(kept) - 1}\x00"

    masked = _GLOSS.sub(stash, text)
    n_before = len(_HAS_HANJA.findall(masked))
    converted = _hanja.translate(masked, "substitution")

    def restore(m: re.Match) -> str:
        return kept[int(m.group(1))]

    out = re.sub(r"\x00(\d+)\x00", restore, converted)
    n_after = len(_HAS_HANJA.findall(re.sub(r"\x00\d+\x00", "", converted)))
    return out, max(0, n_before - n_after)
