"""HWP 3.0 (한글 3.0) 본문 추출 — 2002년 대상(「2003 외교백서」).

이 포맷은 OLE 복합문서가 아니라 자체 구조라 HWP 5.0 파서로는 열리지 않는다.

알아낸 것 (2026-08-15, 실측)
  1. 머리 128바이트 + 문서요약 뒤, **헤더 없는 deflate**(raw inflate)로 본문이
     통째로 압축돼 있다. 시작 위치는 파일마다 조금 다르므로 범위를 훑어 가장
     많이 풀리는 지점을 고른다.
  2. 글자는 2바이트 **조합형(johab)** 인데 **바이트 순서가 뒤집혀 있다.**
     글꼴·스타일 이름은 정순이라 그것만 읽고 본문이 깨지는 착시가 생긴다.
     확인: '미국'을 뒤집은 바이트열이 본문에 164회, 정순은 0회.
  3. 본문에는 문단마다 서식 정보가 섞여 있어 통짜로 훑으면 글자 위치가 어긋난다.
     글자로 읽히는 코드가 일정 길이 이상 이어지는 구간만 건진다.
"""

import zlib
from pathlib import Path

SIGNATURE = b"HWP Document File V3.00"

# 압축 시작점 탐색 범위. 머리(128) + 문서요약(1024) 뒤에서 시작하고,
# 그 사이 정보블록 길이가 파일마다 달라 고정값을 쓸 수 없다.
_DEFLATE_SEARCH = range(1140, 1400)

# 글자 구간으로 인정할 최소 길이. 짧게 잡으면 서식 바이트가 글자로 섞이고,
# 길게 잡으면 짧은 제목 줄이 통째로 버려진다.
_MIN_RUN = 3


def is_hwp3(path: Path) -> bool:
    with open(path, "rb") as f:
        return f.read(len(SIGNATURE)) == SIGNATURE


def _inflate_body(raw: bytes) -> bytes:
    best = b""
    for off in _DEFLATE_SEARCH:
        try:
            out = zlib.decompressobj(-15).decompress(raw[off:])
            if len(out) > len(best):
                best = out
        except Exception:
            pass
    return best


def _to_char(code: int) -> str | None:
    """글자 코드 하나를 문자로. 글자가 아니면 None."""
    if code & 0x8000:
        try:
            ch = code.to_bytes(2, "big").decode("johab")
        except Exception:
            return None
        return ch if len(ch) == 1 else None
    if 32 <= code < 127:
        return chr(code)
    if code in (0x0A, 0x0D):
        return "\n"
    return None


def _harvest(body: bytes) -> str:
    """바이트 순서를 뒤집어 읽으며 글자가 이어지는 구간만 건진다."""
    pieces: list[str] = []
    run: list[str] = []
    for i in range(0, len(body) - 1, 2):
        code = (body[i + 1] << 8) | body[i]   # ← 저장은 역순이다
        ch = _to_char(code)
        if ch is not None:
            run.append(ch)
        else:
            if len(run) >= _MIN_RUN:
                pieces.append("".join(run))
            run = []
    if len(run) >= _MIN_RUN:
        pieces.append("".join(run))
    return "\n".join(pieces)


def read_hwp3_text(path: Path) -> tuple[str, str | None]:
    """(본문, 오류) 반환."""
    raw = Path(path).read_bytes()
    if not raw.startswith(SIGNATURE):
        return "", "HWP 3.0 서명이 아님"

    body = _inflate_body(raw)
    if not body:
        return "", "본문 압축을 풀지 못함"

    text = _harvest(body)
    if not text.strip():
        return "", "본문 텍스트를 얻지 못함"
    return text, None
