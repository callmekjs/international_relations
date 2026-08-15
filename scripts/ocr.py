"""스캔본 PDF의 OCR — 2017·2019년 대상.

두 해는 텍스트 레이어가 없는 스캔 이미지다. 하필 2017년이 정권 교체 해
(박근혜→문재인)라 건너뛸 수 없다.

OCR 은 오탈자를 낸다. 이 프로젝트는 그것을 숨기지 않고 두 가지로 감당한다.
  1) 필요한 것은 기조 절 두어 쪽뿐이라, 그 쪽만 사람이 원문과 대조해 고친다.
  2) 고치기 전에는 `editions[].status` 를 blocked 로 두어 화면이 빈칸으로 보인다.

한 번 돌리는 데 몇 분 걸리므로 결과를 파일에 넣어두고 다시 쓰지 않는다.
"""

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

import fitz

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_ROOT = PROJECT_ROOT / "text" / ".ocr_cache"

OCR_DPI = 300      # 200 은 본문 작은 글자가 뭉개지고, 400 은 느린 만큼 이득이 없다
OCR_LANG = "kor"
OCR_PSM = "6"      # 한 덩어리 문단으로 취급 — 2단 조판이 아닌 백서 본문에 맞다

_TESS_CANDIDATES = (
    os.environ.get("TESSERACT_EXE"),
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    "tesseract",
)
_TESSDATA_CANDIDATES = (
    os.environ.get("TESSDATA_PREFIX"),
    str(Path(os.environ.get("LOCALAPPDATA", "")) / "tessdata"),
    r"C:\Program Files\Tesseract-OCR\tessdata",
)


def find_tesseract() -> str | None:
    for c in _TESS_CANDIDATES:
        if not c:
            continue
        if c == "tesseract" or Path(c).exists():
            return c
    return None


def find_tessdata() -> str | None:
    """kor.traineddata 가 실제로 있는 폴더를 고른다."""
    for c in _TESSDATA_CANDIDATES:
        if c and (Path(c) / f"{OCR_LANG}.traineddata").exists():
            return c
    return None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _run_tesseract(exe: str, img: Path, env: dict) -> str:
    out = subprocess.run(
        [exe, str(img), "stdout", "-l", OCR_LANG, "--psm", OCR_PSM],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    if out.returncode != 0:
        raise RuntimeError((out.stderr or "").strip()[:300])
    return (out.stdout or "").strip()


def ocr_pdf(path: Path, spread_min_width: int, progress=None) -> tuple[list[dict], str | None]:
    """스캔 PDF 를 쪽별 텍스트로. 반환 형태는 formats.read_pdf 와 같다."""
    exe = find_tesseract()
    if not exe:
        return [], "tesseract 를 찾지 못함 — 설치 후 TESSERACT_EXE 로 지정할 수 있다"
    tessdata = find_tessdata()
    if not tessdata:
        return [], f"{OCR_LANG}.traineddata 를 찾지 못함 — 언어팩이 필요하다"

    cache_path = CACHE_ROOT / f"{_sha256(path)}.json"
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8")), None
        except Exception:
            pass  # 캐시가 깨졌으면 다시 돌린다

    env = {**os.environ, "TESSDATA_PREFIX": tessdata}
    pages: list[dict] = []
    doc = fitz.open(path)
    try:
        zoom = fitz.Matrix(OCR_DPI / 72, OCR_DPI / 72)
        with tempfile.TemporaryDirectory() as td:
            img = Path(td) / "page.png"
            for i in range(doc.page_count):
                page = doc[i]
                r = page.rect
                if r.width > spread_min_width:
                    mid = r.x0 + r.width / 2
                    clips = [("L", fitz.Rect(r.x0, r.y0, mid, r.y1)),
                             ("R", fitz.Rect(mid, r.y0, r.x1, r.y1))]
                else:
                    clips = [(None, r)]
                for half, clip in clips:
                    page.get_pixmap(matrix=zoom, clip=clip).save(img)
                    try:
                        text = _run_tesseract(exe, img, env)
                    except RuntimeError as exc:
                        return [], f"{i + 1}쪽 OCR 실패: {exc}"
                    pages.append({"page": i + 1, "half": half, "text": text})
                if progress:
                    progress(i + 1, doc.page_count)
    finally:
        doc.close()

    if not any(p["text"].strip() for p in pages):
        return [], "OCR 결과가 비어 있음"

    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
    return pages, None
