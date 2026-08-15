"""MS Word 97 (.doc) 본문 추출.

1998년 대상(「1999 외교백서」) 8개 파일이 이 포맷이다. LibreOffice 가 없어
외부 변환기를 쓸 수 없으므로 파일 구조를 직접 읽는다.

읽는 순서
    WordDocument 스트림의 FIB(File Information Block)
      → 조각표(piece table)가 어느 Table 스트림에 있는지(fWhichTblStm)
      → Table 스트림의 Clx 안에서 Pcdt 를 찾고
      → 조각마다 본문 스트림의 어느 위치에서 몇 글자인지 읽는다

Word 는 본문을 한 덩어리로 두지 않고 편집 이력에 따라 여러 조각으로 흩어
놓는다. 조각표를 따라가지 않고 스트림을 통으로 읽으면 문장이 뒤섞이거나
삭제된 옛 문장이 섞여 들어온다.
"""

import olefile

# FIB 안의 자리. Word 97(nFib 193) 기준 고정값이다.
_OFF_FLAGS = 0x000A     # bit 0x0200 이 서면 조각표가 1Table, 아니면 0Table
_OFF_CCP_TEXT = 0x004C  # 본문(머리말·각주 제외) 글자 수
_OFF_FC_CLX = 0x01A2    # Table 스트림 안 Clx 의 시작
_OFF_LCB_CLX = 0x01A6   # Clx 의 길이

_PRC = 0x01   # 서식 묶음 — 본문이 아니므로 건너뛴다
_PCDT = 0x02  # 조각표

# Word 의 제어문자. 필드 코드(계산식·상호참조)는 결과만 남기고 지시부는 버린다.
_FIELD_BEGIN, _FIELD_SEP, _FIELD_END = "\x13", "\x14", "\x15"
_PARA_END, _CELL_END, _LINE_BREAK, _PAGE_BREAK = "\r", "\x07", "\x0b", "\x0c"


def _u16(b: bytes, off: int) -> int:
    return int.from_bytes(b[off:off + 2], "little")


def _u32(b: bytes, off: int) -> int:
    return int.from_bytes(b[off:off + 4], "little")


def _find_pcdt(clx: bytes) -> bytes | None:
    """Clx 를 훑어 조각표(Pcdt) 본체를 돌려준다."""
    pos = 0
    while pos < len(clx):
        kind = clx[pos]
        pos += 1
        if kind == _PRC:
            cb = _u16(clx, pos)
            pos += 2 + cb
        elif kind == _PCDT:
            lcb = _u32(clx, pos)
            pos += 4
            return clx[pos:pos + lcb]
        else:
            return None
    return None


def _decode_pieces(doc: bytes, plc: bytes, ccp_text: int) -> str:
    """조각표(PlcPcd)를 따라 본문을 순서대로 잇는다."""
    n = (len(plc) - 4) // 12          # CP 는 n+1 개(4바이트), 조각 서술은 n 개(8바이트)
    if n <= 0:
        return ""
    cps = [_u32(plc, i * 4) for i in range(n + 1)]
    out: list[str] = []

    for i in range(n):
        cp_start, cp_end = cps[i], cps[i + 1]
        if cp_start >= ccp_text:      # 본문 뒤쪽은 각주·머리말·꼬리말이라 버린다
            break
        cp_end = min(cp_end, ccp_text)
        length = cp_end - cp_start
        if length <= 0:
            continue

        pcd = plc[4 * (n + 1) + i * 8:4 * (n + 1) + i * 8 + 8]
        fc = _u32(pcd, 2)
        if fc & 0x40000000:           # 1바이트 조각 — 한글은 여기 오지 않는다
            off = (fc & 0x3FFFFFFF) // 2
            raw = doc[off:off + length]
            out.append(raw.decode("cp1252", errors="replace"))
        else:                         # 2바이트 조각 — UTF-16LE
            raw = doc[fc:fc + length * 2]
            out.append(raw.decode("utf-16-le", errors="replace"))

    return "".join(out)


def _strip_controls(s: str) -> str:
    """필드 지시부를 걷어내고 제어문자를 줄바꿈·공백으로 바꾼다."""
    out: list[str] = []
    depth = 0          # 필드 중첩 깊이
    in_result = False  # 필드의 '결과' 구간인가

    for ch in s:
        if ch == _FIELD_BEGIN:
            depth += 1
            in_result = False
            continue
        if ch == _FIELD_SEP:
            in_result = True
            continue
        if ch == _FIELD_END:
            depth = max(0, depth - 1)
            in_result = False
            continue
        if depth and not in_result:
            continue  # 필드 지시부(‘PAGE’ 같은 것)는 본문이 아니다

        if ch in (_PARA_END, _LINE_BREAK, _PAGE_BREAK):
            out.append("\n")
        elif ch == _CELL_END:
            out.append("\t")
        elif ch == "\x00" or (ord(ch) < 32 and ch not in "\t\n"):
            continue
        else:
            out.append(ch)

    return "".join(out)


def read_doc_text(path) -> tuple[str, str | None]:
    """(본문, 오류) 반환."""
    if not olefile.isOleFile(str(path)):
        return "", "OLE 복합문서가 아님 — Word 97 형식이 아니다"

    ole = olefile.OleFileIO(str(path))
    try:
        names = {"/".join(e) for e in ole.listdir()}
        if "WordDocument" not in names:
            return "", "WordDocument 스트림 없음"
        doc = ole.openstream("WordDocument").read()

        flags = _u16(doc, _OFF_FLAGS)
        table_name = "1Table" if (flags & 0x0200) else "0Table"
        if table_name not in names:
            return "", f"{table_name} 스트림 없음"
        table = ole.openstream(table_name).read()

        ccp_text = _u32(doc, _OFF_CCP_TEXT)
        fc_clx, lcb_clx = _u32(doc, _OFF_FC_CLX), _u32(doc, _OFF_LCB_CLX)
        if lcb_clx == 0:
            return "", "조각표(Clx) 없음"

        plc = _find_pcdt(table[fc_clx:fc_clx + lcb_clx])
        if plc is None:
            return "", "Clx 안에서 조각표(Pcdt)를 찾지 못함"

        text = _strip_controls(_decode_pieces(doc, plc, ccp_text))
    finally:
        ole.close()

    if not text.strip():
        return "", "본문 텍스트를 얻지 못함"
    return text, None
