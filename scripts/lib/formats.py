"""포맷별 텍스트 리더.

각 리더는 (페이지 텍스트 리스트, 오류메시지) 를 돌려준다.
페이지 하나는 dict: {"page": 물리쪽번호, "half": None|"L"|"R", "text": str}

「외교백서」는 여섯 세대의 포맷으로 발간됐고, 세대마다 읽는 법이 다르다.
연도로 분기하지 않는다 — 파일을 열어 실제 성질을 보고 판단한다
(같은 2015년 안에서도 1장은 단면, 2~7장은 좌우 펼침이다).
"""

import re
import zlib
from pathlib import Path

import fitz  # PyMuPDF
import olefile

# 좌우 펼침 판정 기준(pt). 단면은 실측 421~533, 펼침은 1020~1066 이라 그 사이면 무엇이든 갈린다.
SPREAD_MIN_WIDTH = 700

# 텍스트 레이어가 있다고 볼 최소 글자 수(쪽당). 스캔본은 0 이 나온다.
TEXT_LAYER_MIN_CHARS_PER_PAGE = 20

# 스캔본을 만나면 OCR 로 넘어갈지. 몇 분씩 걸리므로 끄고 돌릴 수 있게 둔다.
ENABLE_OCR = True


def _ocr_progress(done: int, total: int) -> None:
    print(f"      OCR {done}/{total}쪽", end="\r", flush=True)


# ── PDF ──────────────────────────────────────────────────────────────────────

# 세로쓰기 머리글을 블록 크기로 걸러내는 방법을 시험했다가 물렸다(2026-08-15).
# 백서는 쪽 옆에 장·절 제목을 세로로 앉히고, 그 글자가 본문 문장 사이로 한 자씩
# 끼어든다('…영사서비스강화 정 / 세 / 및외교정책에…'). 좁고 긴 블록을 버리면
# 잡히긴 하는데 **본문도 함께 깎였다** — 2005년 인용 세 건이 문장 중간에서
# 끊겼고 2018·2020~2025년은 글자 수가 10~30% 줄었다. verify 가 이것을 잡았다.
#
# 머리글 몇 개를 지우자고 본문을 잃을 수는 없다. 세로 머리글이 끼어든 자리는
# 인용에서 (…) 로 끊는다 — 생략 표시이자 '여기서 머리글이 끼어든다'는 기록이다.


def _page_text(page, clip) -> str:
    return page.get_text("text", clip=clip, sort=True)


def _page_blocks(page, clip) -> list[str]:
    """PDF 가 스스로 묶어 놓은 덩어리를 그대로 돌려준다.

    문단을 '빈 줄로 나누기'로 잡으면 안 된다. 추출본은 줄마다 빈 줄이 들어가서
    모든 줄이 문단이 되어버린다(2026-08-15 실측: 4,615문단 중 98%가 100자 미만,
    한 문장이 세 조각으로 잘렸다).

    블록은 PDF 가 조판할 때 묶어둔 단위라 문단에 가깝다. **순서는 손대지 않는다** —
    다시 정렬하면 문단이 뒤섞인다(같은 날 겪었다)."""
    try:
        blocks = page.get_text("blocks", clip=clip, sort=True)
    except Exception:
        return []
    out = []
    for b in blocks:
        t = (b[4] or "").strip()
        if t:
            out.append(re.sub(r"\s*\n\s*", " ", t))   # 블록 안의 줄바꿈은 공백으로
    return out


def read_pdf(path: Path) -> tuple[list[dict], str | None]:
    """PDF를 쪽별 텍스트로 읽는다. 폭이 넓은 쪽은 좌·우 반쪽으로 갈라
    읽기 순서를 맞춘다(펼침 스캔은 한 쪽에 두 면이 들어 있다)."""
    pages: list[dict] = []
    try:
        doc = fitz.open(path)
    except Exception as exc:
        return [], f"PDF 열기 실패: {exc}"

    try:
        for i in range(doc.page_count):
            page = doc[i]
            rect = page.rect
            if rect.width > SPREAD_MIN_WIDTH:
                mid = rect.x0 + rect.width / 2
                left = fitz.Rect(rect.x0, rect.y0, mid, rect.y1)
                right = fitz.Rect(mid, rect.y0, rect.x1, rect.y1)
                pages.append({"page": i + 1, "half": "L", "text": _page_text(page, left),
                              "blocks": _page_blocks(page, left)})
                pages.append({"page": i + 1, "half": "R", "text": _page_text(page, right),
                              "blocks": _page_blocks(page, right)})
            else:
                pages.append({"page": i + 1, "half": None, "text": _page_text(page, rect),
                              "blocks": _page_blocks(page, rect)})
        n_physical = doc.page_count
    finally:
        doc.close()

    total = sum(len(p["text"].strip()) for p in pages)
    if n_physical and total < n_physical * TEXT_LAYER_MIN_CHARS_PER_PAGE:
        # 스캔 이미지 PDF. 조용히 빈 결과를 넘기면 하류가 "내용이 없는 해"로 오해한다.
        if not ENABLE_OCR:
            return [], f"텍스트 레이어 없음 (스캔본, {n_physical}쪽에서 {total}자) — OCR 필요"
        from ocr import ocr_pdf

        pages, err = ocr_pdf(path, SPREAD_MIN_WIDTH, progress=_ocr_progress)
        if err:
            return [], f"텍스트 레이어 없음 → OCR 시도 실패: {err}"
        for p in pages:
            p["ocr"] = True
        return pages, None

    return pages, None


# ── HWP 5.0 (OLE 복합문서) ───────────────────────────────────────────────────

_HWPTAG_PARA_TEXT = 67  # HWPTAG_BEGIN(16) + 51

# HWP 5.0 본문의 제어문자는 세 종류다. 확장·인라인 제어는 자기 자신을 포함해
# 8 WCHAR 를 차지하므로 그만큼 건너뛰어야 뒤 글자가 밀리지 않는다.
_CTRL_SKIP8 = frozenset([1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12,
                         14, 15, 16, 17, 18, 19, 20, 21, 22, 23])
_CTRL_NEWLINE = frozenset([10, 13])


def _hwp5_is_compressed(ole: olefile.OleFileIO) -> bool:
    header = ole.openstream("FileHeader").read()
    if len(header) < 40:
        return False
    flags = int.from_bytes(header[36:40], "little")
    return bool(flags & 0x01)


def _hwp5_records(buf: bytes):
    """레코드 스트림을 (tag_id, payload) 로 훑는다."""
    pos, n = 0, len(buf)
    while pos + 4 <= n:
        header = int.from_bytes(buf[pos:pos + 4], "little")
        pos += 4
        tag_id = header & 0x3FF
        size = (header >> 20) & 0xFFF
        if size == 0xFFF:
            if pos + 4 > n:
                break
            size = int.from_bytes(buf[pos:pos + 4], "little")
            pos += 4
        yield tag_id, buf[pos:pos + size]
        pos += size


def _hwp5_decode_para(payload: bytes) -> str:
    """PARA_TEXT 페이로드(UTF-16LE + 제어문자)를 사람이 읽는 글자만 남긴다."""
    out: list[str] = []
    i, n = 0, len(payload) // 2
    while i < n:
        code = int.from_bytes(payload[i * 2:i * 2 + 2], "little")
        if code in _CTRL_SKIP8:
            i += 8
            continue
        if code in _CTRL_NEWLINE:
            out.append("\n")
            i += 1
            continue
        if code < 32:
            i += 1
            continue
        out.append(chr(code))
        i += 1
    return "".join(out)


def read_hwp5(path: Path) -> tuple[list[dict], str | None]:
    """HWP 5.0 을 읽는다. 쪽 경계 정보가 파일에 없으므로 구역(Section)을
    한 '쪽'으로 취급하고 half 는 두지 않는다 — 출처 표기에서 쪽수를 쓸 수 없다는
    뜻이라 authoring 단계에서 사람이 인쇄본 쪽수를 적는다."""
    if not olefile.isOleFile(str(path)):
        from hwp3 import is_hwp3, read_hwp3_text

        if is_hwp3(path):
            text, err = read_hwp3_text(path)
            if err:
                return [], f"HWP 3.0: {err}"
            return [{"page": 1, "half": None, "text": text}], None
        return [], "OLE 복합문서도 HWP 3.0 도 아님 — 알 수 없는 형식"

    try:
        ole = olefile.OleFileIO(str(path))
    except Exception as exc:
        return [], f"HWP 열기 실패: {exc}"

    try:
        compressed = _hwp5_is_compressed(ole)
        sections = sorted(
            (e for e in ole.listdir() if len(e) == 2 and e[0] == "BodyText"),
            key=lambda e: int("".join(c for c in e[1] if c.isdigit()) or 0),
        )
        if not sections:
            return [], "BodyText 구역 없음"

        pages: list[dict] = []
        for idx, entry in enumerate(sections, start=1):
            raw = ole.openstream(entry).read()
            if compressed:
                try:
                    raw = zlib.decompress(raw, -15)  # raw inflate (zlib 헤더 없음)
                except zlib.error as exc:
                    return [], f"{'/'.join(entry)} 압축 해제 실패: {exc}"
            chunks = [_hwp5_decode_para(payload)
                      for tag, payload in _hwp5_records(raw) if tag == _HWPTAG_PARA_TEXT]
            pages.append({"page": idx, "half": None, "text": "\n".join(chunks)})
    finally:
        ole.close()

    if not any(p["text"].strip() for p in pages):
        return [], "본문 텍스트를 얻지 못함"
    return pages, None


# ── MS Word 97 (.doc) ────────────────────────────────────────────────────────

def read_doc(path: Path) -> tuple[list[dict], str | None]:
    """Word 97 문서. 파일에 쪽 경계가 없으므로 한 덩어리로 다룬다 —
    출처의 쪽수는 authoring 단계에서 사람이 인쇄본을 보고 적는다."""
    from word97 import read_doc_text

    text, err = read_doc_text(path)
    if err:
        return [], err
    return [{"page": 1, "half": None, "text": text}], None


# ── 아직 지원하지 않는 포맷 ──────────────────────────────────────────────────

def read_unsupported(path: Path) -> tuple[list[dict], str | None]:
    return [], f"미지원 포맷 {path.suffix} — 전용 파서 필요"


READERS = {
    ".pdf": read_pdf,
    ".hwp": read_hwp5,   # HWP 3.0 이면 read_hwp5 가 "OLE 아님"으로 걸러낸다
    ".doc": read_doc,
}


def read_any(path: Path) -> tuple[list[dict], str | None]:
    return READERS.get(path.suffix.lower(), read_unsupported)(path)
