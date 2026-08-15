"""
정권별 묶기 — 검사를 통과한 해만 모아 corpus/ 를 만든다.

    python scripts/corpus.py
    python scripts/corpus.py --out etl_test --corpus corpus_test

**통과한 해만 들어간다.** corpus/ 가 존재한다는 것 자체가 "검사를 다 통과했다"는
뜻이 되게 하는 것이 목적이다. 미완성 자료가 분석·지식그래프로 흘러드는 것을 막는다.

산출물
    corpus/sentences.jsonl        전체 (본문 문장 + 부록 표줄)
    corpus/by-admin/<정권>.jsonl  정권별
    corpus/toc.jsonl              목차 (구조 검증용)
    corpus/index.json             몇 개년·몇 문장·어디가 OCR 유래인지
"""

import argparse
import io
import json
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from stage_io import PROJECT_ROOT, write_json_atomic   # noqa: E402

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ADMIN_ORDER = ["노태우", "김영삼", "김대중", "노무현", "이명박",
               "박근혜", "문재인", "윤석열", "이재명"]


def read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="etl_test", help="연도별 산출물이 있는 곳")
    ap.add_argument("--corpus", default="corpus", help="묶어서 낼 곳")
    ap.add_argument("--allow-unchecked", action="store_true",
                    help="검사를 통과하지 않은 해도 넣는다. 쓸 일이 없어야 한다")
    a = ap.parse_args()

    out_root = PROJECT_ROOT / a.out
    corpus_root = PROJECT_ROOT / a.corpus

    years = sorted(int(d.name) for d in out_root.iterdir()
                   if d.is_dir() and d.name.isdigit())
    if not years:
        print(f"[ERROR] {out_root} 에 연도 폴더가 없다.")
        sys.exit(1)

    # 검사를 통과했는지 확인한다. check.py 를 먼저 돌려야 한다.
    if not a.allow_unchecked:
        import subprocess
        cmd = [sys.executable, str(Path(__file__).parent / "check.py"),
               "--out", a.out] + sum([["--year", str(y)] for y in years], [])
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            print("[중단] 검사를 통과하지 못한 해가 있다. corpus 를 만들지 않는다.\n")
            print("\n".join(l for l in (r.stdout or "").splitlines()
                            if "오류" in l or "년 —" in l))
            sys.exit(1)
        print("검사 통과 확인됨\n")

    if corpus_root.exists():
        shutil.rmtree(corpus_root)
    (corpus_root / "by-admin").mkdir(parents=True)

    all_rows: list[dict] = []
    toc_rows: list[dict] = []
    by_admin: dict[str, list[dict]] = defaultdict(list)
    per_year: dict[int, dict] = {}

    for y in years:
        d = out_root / str(y)
        rows = read_jsonl(d / "sentences.jsonl")
        toc = read_jsonl(d / "toc.jsonl")
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        admin = meta.get("administration")

        for r in rows:
            all_rows.append(r)
            if admin:
                by_admin[admin].append(r)
        toc_rows.extend(toc)

        units = Counter(r.get("단위", "문장") for r in rows)
        per_year[y] = {
            "정권": admin,
            "쪽": meta["counts"]["pages"],
            "문장": units.get("문장", 0),
            "표줄": units.get("표줄", 0),
            "목차": len(toc),
            "OCR유래": sum(1 for r in rows if r.get("OCR유래")),
            "한자변환된문장": sum(1 for r in rows if r.get("한글") and r["한글"] != r["원문"]),
        }
        print(f"  {y}  {admin:<4} 문장 {units.get('문장',0):>5} · "
              f"표줄 {units.get('표줄',0):>5} · 목차 {len(toc):>3}")

    def dump(path: Path, rows: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    dump(corpus_root / "sentences.jsonl", all_rows)
    dump(corpus_root / "toc.jsonl", toc_rows)
    for admin in ADMIN_ORDER:
        if by_admin.get(admin):
            dump(corpus_root / "by-admin" / f"{admin}.jsonl", by_admin[admin])

    index = {
        "builtFrom": a.out,
        "years": years,
        "counts": {
            "years": len(years),
            "records": len(all_rows),
            "sentences": sum(1 for r in all_rows if r.get("단위", "문장") == "문장"),
            "tableLines": sum(1 for r in all_rows if r.get("단위") == "표줄"),
            "tocEntries": len(toc_rows),
            "ocrDerived": sum(1 for r in all_rows if r.get("OCR유래")),
        },
        "byAdministration": {a_: len(v) for a_, v in
                             sorted(by_admin.items(), key=lambda kv: ADMIN_ORDER.index(kv[0]))},
        "perYear": per_year,
    }
    write_json_atomic(corpus_root / "index.json", index)

    print(f"\n{'=' * 56}")
    print(f"  corpus → {corpus_root}")
    print(f"  {len(years)}개년 · 레코드 {len(all_rows):,}개 "
          f"(문장 {index['counts']['sentences']:,} · 표줄 {index['counts']['tableLines']:,})")
    for a_, n in index["byAdministration"].items():
        print(f"    {a_:<5} {n:>7,}")
    print(f"{'=' * 56}")


if __name__ == "__main__":
    main()
