"""
점검 1층 — 한 해가 온전한지 본다. 통과해야 다음 해로 넘어간다.

    python scripts/check.py --year 2013
    python scripts/check.py --year 2013 --delete-on-fail
    python scripts/check.py --all
    python scripts/check.py --year 2013 --save-baseline

전문 ETL 은 11,324쪽이라 사람이 눈으로 못 본다. '글자가 맞나'를 볼 수 없으므로
**'빠진 게 없나'**를 본다.

가장 중요한 것은 **기준선 비교**다. 통과한 결과의 숫자(쪽·문장·글자)를 저장해
두고, 다시 뽑았을 때 크게 달라지면 세운다. 2026-08-15 에 '개선'이라고 넣은
코드가 본문을 10~30% 날린 적이 두 번 있는데, 기준선이 있었으면 그 자리에서
잡혔을 것이다.
"""

CHECK_VERSION = "v0.1"

import argparse
import io
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

import fitz                                    # noqa: E402
from formats import SPREAD_MIN_WIDTH           # noqa: E402
from normalize import normalize_for_match      # noqa: E402
from stage_io import PROJECT_ROOT, write_json_atomic  # noqa: E402

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DATA_ROOT = PROJECT_ROOT / "data"
READABLE = {".pdf", ".hwp", ".doc"}
REFERENCE = PROJECT_ROOT / "docs" / "reference" / "기조절-141개-정답지.tsv"

# 기준선에서 이만큼 벗어나면 세운다. 조판이 조금 달라져도 5%는 안 넘는다.
BASELINE_TOLERANCE = 0.05

# 빈 쪽 비율. 스캔 실패·추출 실패의 징후다.
EMPTY_PAGE_WARN = 0.05
EMPTY_PAGE_FAIL = 0.20

# 문장 길이. 문단·줄이 잘못 잡히면 짧은 것만 잔뜩 나온다.
SHORT_SENT_WARN = 0.60


def logical_pages(path: Path) -> int:
    """원본이 실제로 몇 쪽인가. 좌우 펼침은 2쪽으로 센다 — 추출과 같은 기준."""
    if path.suffix.lower() != ".pdf":
        return 0        # HWP·DOC 는 파일에 쪽 개념이 없다
    try:
        doc = fitz.open(path)
        n = sum(2 if doc[i].rect.width > SPREAD_MIN_WIDTH else 1 for i in range(doc.page_count))
        doc.close()
        return n
    except Exception:
        return -1


def load_reference(year: int) -> list[str]:
    """그 해 기조 절 인용문. 사람이 원본을 보고 확인한 것이라 시험지로 쓴다."""
    if not REFERENCE.exists():
        return []
    out, header = [], None
    for line in REFERENCE.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cols = line.split("\t")
        if header is None:
            header = cols
            continue
        row = dict(zip(header, cols + [""] * (len(header) - len(cols))))
        if row.get("coverageYear", "").strip() == str(year):
            q = (row.get("quote") or "").strip()
            if q and "(…)" not in q:      # 생략 표시가 있는 것은 그대로 못 찾는다
                out.append(q)
    return out


def check_year(year: int, out_root: Path, baseline: dict) -> tuple[str, list[tuple[str, str, str]]]:
    rows: list[tuple[str, str, str]] = []      # (등급, 항목, 설명)

    d = out_root / str(year)
    for name in ("pages.jsonl", "sentences.jsonl", "meta.json"):
        if not (d / name).exists():
            rows.append(("오류", "산출물", f"{name} 가 없다 — etl.py 를 돌려야 한다"))
            return "오류", rows

    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    pages = [json.loads(l) for l in (d / "pages.jsonl").read_text(encoding="utf-8").splitlines()]
    sents = [json.loads(l) for l in (d / "sentences.jsonl").read_text(encoding="utf-8").splitlines()]

    # 1. 파일 누락 — 폴더의 모든 파일이 처리됐나
    on_disk = sorted(f.name for f in (DATA_ROOT / str(year)).iterdir()
                     if f.is_file() and f.suffix.lower() in READABLE)
    handled = sorted(s["file"] for s in meta["sources"])
    missing = set(on_disk) - set(handled)
    if missing:
        rows.append(("오류", "파일 누락", f"{len(missing)}개가 처리되지 않았다: {sorted(missing)[:3]}"))
    else:
        rows.append(("OK", "파일", f"{len(on_disk)}개 모두 처리"))

    failed = [s for s in meta["sources"] if s["status"] == "failed"]
    if failed:
        rows.append(("오류", "읽기 실패",
                     f"{len(failed)}개 — {failed[0]['file']}: {failed[0].get('error','')[:50]}"))

    # 2. 쪽 누락 — 원본 쪽 수와 맞나
    want = sum(logical_pages(DATA_ROOT / str(year) / s["file"]) for s in meta["sources"]
               if s["status"] == "ok")
    got = sum(s["pages"] for s in meta["sources"] if s["status"] == "ok" and
              (DATA_ROOT / str(year) / s["file"]).suffix.lower() == ".pdf")
    if want > 0:
        if want == got:
            rows.append(("OK", "쪽 수", f"{got}쪽 — 원본과 일치"))
        else:
            rows.append(("오류", "쪽 수", f"원본 {want}쪽인데 {got}쪽만 뽑혔다"))

    # 3. 빈 쪽 — 추출이 실패한 쪽
    empty = sum(1 for p in pages if len(p["원문"].strip()) < 50)
    ratio = empty / len(pages) if pages else 0
    if ratio >= EMPTY_PAGE_FAIL:
        rows.append(("오류", "빈 쪽", f"{empty}/{len(pages)}쪽 ({ratio*100:.0f}%) 이 비었다"))
    elif ratio >= EMPTY_PAGE_WARN:
        rows.append(("미완", "빈 쪽", f"{empty}/{len(pages)}쪽 ({ratio*100:.0f}%)"))
    else:
        rows.append(("OK", "빈 쪽", f"{empty}/{len(pages)}쪽"))

    # 4. 문장 품질 — 짧은 것만 잔뜩이면 나누기가 잘못된 것이다
    lens = sorted(len(s["원문"]) for s in sents)
    if not lens:
        rows.append(("오류", "문장", "하나도 없다"))
    else:
        short = sum(1 for x in lens if x < 60) / len(lens)
        mid = lens[len(lens) // 2]
        if short >= SHORT_SENT_WARN:
            rows.append(("오류", "문장 길이",
                         f"60자 미만이 {short*100:.0f}% — 문장 나누기가 잘못됐을 수 있다"))
        else:
            rows.append(("OK", "문장", f"{len(lens)}개 · 중앙 {mid}자 · 60자미만 {short*100:.0f}%"))

    # 5. 장 배정
    no_ch = sum(1 for s in sents if not s.get("장"))
    if sents:
        r = no_ch / len(sents)
        lvl = "오류" if r > 0.15 else ("미완" if r > 0.03 else "OK")
        rows.append((lvl, "장 배정", f"장 없는 문장 {no_ch}개 ({r*100:.0f}%)"))

    # 6. 정답지 대조 — 사람이 확인한 문장이 전문 안에 있나
    ref = load_reference(year)
    if ref:
        body = normalize_for_match(" ".join(s["원문"] for s in sents))
        found = sum(1 for q in ref if normalize_for_match(q) in body)
        if found == len(ref):
            rows.append(("OK", "정답지", f"{found}/{len(ref)}건 모두 들어 있다"))
        elif found >= len(ref) * 0.8:
            rows.append(("미완", "정답지", f"{found}/{len(ref)}건 — 일부가 안 보인다"))
        else:
            rows.append(("오류", "정답지",
                         f"{found}/{len(ref)}건만 있다 — 뭔가 빠뜨렸다"))

    # 7. 기준선 — 지난번 통과한 결과와 얼마나 달라졌나
    base = baseline.get(str(year))
    if base:
        cur = {"pages": meta["counts"]["pages"], "sentences": meta["counts"]["sentences"],
               "chars": meta["counts"]["chars"]}
        drift = []
        for k, v in cur.items():
            b = base.get(k, 0)
            if b and abs(v - b) / b > BASELINE_TOLERANCE:
                drift.append(f"{k} {b:,}→{v:,} ({(v-b)/b*100:+.0f}%)")
        if drift:
            rows.append(("오류", "기준선", " / ".join(drift) + " — 지난번과 크게 다르다"))
        else:
            rows.append(("OK", "기준선", "지난번과 같다"))
    else:
        rows.append(("미완", "기준선", "저장된 것이 없다 — --save-baseline 으로 남긴다"))

    errs = [r for r in rows if r[0] == "오류"]
    todo = [r for r in rows if r[0] == "미완"]
    return ("오류" if errs else "미완" if todo else "끝남"), rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, action="append")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", default="etl_test")
    ap.add_argument("--delete-on-fail", action="store_true",
                    help="오류가 나면 그 해 산출물을 지운다. 반쪽 결과가 남으면 안 된다")
    ap.add_argument("--save-baseline", action="store_true",
                    help="통과한 해의 숫자를 기준선으로 저장한다")
    a = ap.parse_args()

    out_root = PROJECT_ROOT / a.out
    bpath = out_root / "_baseline.json"
    baseline = json.loads(bpath.read_text(encoding="utf-8")) if bpath.exists() else {}

    years = a.year or []
    if a.all:
        years = sorted(int(d.name) for d in out_root.iterdir()
                       if d.is_dir() and d.name.isdigit())
    if not years:
        print("연도를 적어야 한다.  예:  python scripts/check.py --year 2013")
        sys.exit(2)

    mark = {"OK": "OK  ", "미완": "미완 ", "오류": "오류 "}
    failed = 0

    for y in years:
        verdict, rows = check_year(y, out_root, baseline)
        print(f"\n{'=' * 58}\n  {y}년 — {verdict}\n{'=' * 58}")
        for lvl, label, msg in rows:
            print(f"  {mark[lvl]} {label:<10} {msg}")

        if verdict == "오류":
            failed += 1
            if a.delete_on_fail:
                shutil.rmtree(out_root / str(y), ignore_errors=True)
                print(f"\n  → {out_root / str(y)} 를 지웠다. 원인을 고치고 다시 돌린다.")
        elif a.save_baseline:
            meta = json.loads((out_root / str(y) / "meta.json").read_text(encoding="utf-8"))
            baseline[str(y)] = {"pages": meta["counts"]["pages"],
                                "sentences": meta["counts"]["sentences"],
                                "chars": meta["counts"]["chars"]}
            print(f"\n  → 기준선 저장")

    if a.save_baseline:
        write_json_atomic(bpath, baseline)

    print()
    if failed:
        print(f"오류가 있는 해 {failed}개 — 고치기 전에는 다음으로 넘어가지 않는다.")
        sys.exit(1)
    print("통과. 다음 해로 넘어가도 좋다.")


if __name__ == "__main__":
    main()
