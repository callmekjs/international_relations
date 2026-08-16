"""정권이 바뀔 때 외교정책이 정말 급변하는가 — 숫자로 잰다.

    python scripts/policy_shift.py            표로 본다
    python scripts/policy_shift.py --json     web/shift-data.json 으로 내보낸다

**재는 법.** 해마다 '무엇을 얼마나 다뤘나'를 낱말 분포로 만들고, 이웃한 해끼리
얼마나 다른지(코사인 거리) 잰다. 정권이 바뀌는 해에 그 거리가 유난히 크면
급변이 사실이다.

**두 가지를 반드시 걷어낸다.** 안 걷어내면 1.04배(차이 없음)로 나온다 —
2026-08-16 에 실제로 그렇게 나와서 "가설이 틀렸다"고 잘못 결론 낼 뻔했다.

    ① 문체·서식 낱말   '하였다'↔'했다', '외교부는'↔'외교통상부는', '일간·개월·만불'
                       백서 편집자가 바뀌면 달라지는 말이지 정책 변화가 아니다
    ② 원본 결손 연도   2004년(원본 60% 결손). 자료가 없어 생긴 변화를
                       정책 변화로 읽으면 안 된다

걷어낸 뒤: 같은 정권 안 0.1975 · 정권 교체 0.2589 → **1.31배**.
정권 교체 8건 중 6건이 전체 34쌍 중 상위 10위 안에 든다.

**다만 1위는 정권 교체가 아니다** — 2019→2020(코로나) 0.6590 으로 2위의 두 배.
그리고 김영삼→김대중(1997→98)은 24위로 거의 안 변했다(IMF 한복판).
이 두 예외가 이야기를 좋게 만든다.
"""

import argparse
import io
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORPUS = PROJECT_ROOT / "corpus" / "sentences.jsonl"
OUT = PROJECT_ROOT / "web" / "shift-data.json"

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_WORD = re.compile(r"[가-힣]{2,6}")

# 문체·서식 낱말. 정책이 아니라 글투가 바뀐 것을 변화로 세지 않기 위해 뺀다.
_STYLE = re.compile(
    r"(다|음|임|함)$"                                   # 서술어 활용형
    r"|^(외교부|외교통상부|우리나라|정부는|양국간|정상은)"   # 기관·상투어
    r"|(는|은|이|가|를|을|에|와|과|의|도|로|서|간|개월|일간|만불|억불)$"  # 조사·단위
)

# 원본이 크게 빠진 해. config/자료결손.tsv 와 같은 근거다.
SKIP_YEARS = {2004}

# 모든 해에 이만큼 넘게 나오는 말은 주제가 아니다(관련·추진·위하여…).
# 불용어 목록을 사람이 적지 않고 데이터가 정하게 한다.
STOP_DF_RATIO = 0.95
VOCAB_SIZE = 2500


def load() -> tuple[dict, dict]:
    if not CORPUS.exists():
        raise SystemExit(f"[ERROR] {CORPUS} 가 없다. corpus.py 를 먼저 돌린다.")
    by_year, admin_of = defaultdict(Counter), {}
    with CORPUS.open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("단위", "문장") != "문장":
                continue
            y = r["연도"]
            admin_of[y] = r["정권"]
            by_year[y].update(w for w in _WORD.findall(r["한글"] or r["원문"])
                              if not _STYLE.search(w))
    return by_year, admin_of


def build_vocab(by_year: dict, years: list) -> list:
    df = Counter()
    for y in years:
        df.update(set(by_year[y]))
    stop = {w for w, c in df.items() if c >= len(years) * STOP_DF_RATIO}
    total = Counter({w: sum(by_year[y][w] for y in years) for w in df})
    return [w for w, _ in total.most_common(VOCAB_SIZE + len(stop)) if w not in stop][:VOCAB_SIZE]


def cosine_distance(a: list, b: list) -> float:
    dot = sum(x * z for x, z in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(z * z for z in b))
    return 1 - dot / (na * nb + 1e-12)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="web/shift-data.json 으로 내보낸다")
    ap.add_argument("--top", type=int, default=9, help="들고 난 말 몇 개씩 보일까")
    a = ap.parse_args()

    by_year, admin_of = load()
    years = [y for y in sorted(by_year) if y not in SKIP_YEARS]
    vocab = build_vocab(by_year, years)

    def vec(y):
        t = sum(by_year[y][w] for w in vocab) or 1
        return [by_year[y][w] / t for w in vocab]

    V = {y: vec(y) for y in years}
    steps = []
    for x, z in zip(years, years[1:]):
        if z - x != 1:          # 건너뛴 해가 있으면 이웃이 아니다
            continue
        d = cosine_distance(V[x], V[z])
        tx = sum(by_year[x][w] for w in vocab) or 1
        tz = sum(by_year[z][w] for w in vocab) or 1
        delta = sorted(((by_year[z][w] / tz) - (by_year[x][w] / tx), w) for w in vocab)
        steps.append({
            "from": x, "to": z,
            "fromAdmin": admin_of[x], "toAdmin": admin_of[z],
            "swap": admin_of[x] != admin_of[z],
            "distance": round(d, 4),
            "arrived": [w for _, w in delta[-a.top:][::-1]],
            "left": [w for _, w in delta[:a.top]],
        })

    inside = [s for s in steps if not s["swap"]]
    across = [s for s in steps if s["swap"]]
    mi = sum(s["distance"] for s in inside) / len(inside)
    ma = sum(s["distance"] for s in across) / len(across)
    ranked = sorted(steps, key=lambda s: -s["distance"])
    for i, s in enumerate(ranked, 1):
        s["rank"] = i

    print(f"낱말 {len(vocab)}개 · {years[0]}~{years[-1]} · 제외 {sorted(SKIP_YEARS)}\n")
    print("=" * 74)
    print("해마다 앞해와 얼마나 달라졌나")
    print("=" * 74)
    for s in steps:
        bar = "█" * int(s["distance"] * 90)
        mark = f"  ← {s['fromAdmin']} → {s['toAdmin']}" if s["swap"] else ""
        print(f"  {s['from']}→{s['to']}  {s['distance']:.4f}  {bar}{mark}")

    print("\n" + "=" * 74)
    print(f"같은 정권 안   평균 {mi:.4f}  ({len(inside)}쌍)")
    print(f"정권 교체      평균 {ma:.4f}  ({len(across)}쌍)")
    print(f"→ 정권 교체 때 {ma/mi:.2f}배 크게 달라진다")
    print("=" * 74)

    print("\n정권 교체 8건의 순위")
    for s in sorted(across, key=lambda s: s["rank"]):
        print(f"  {s['from']}→{s['to']}  {s['distance']:.4f}  "
              f"{s['fromAdmin']}→{s['toAdmin']}   전체 {len(steps)}쌍 중 {s['rank']}위")

    print("\n같은 정권 안인데 크게 변한 해")
    for s in sorted(inside, key=lambda s: s["rank"])[:5]:
        print(f"  {s['from']}→{s['to']}  {s['distance']:.4f}  {s['fromAdmin']}   {s['rank']}위")

    print("\n" + "=" * 74)
    print("정권 교체 때 들고 난 말")
    print("=" * 74)
    for s in sorted(across, key=lambda s: s["rank"])[:4]:
        print(f"\n  {s['from']}({s['fromAdmin']}) → {s['to']}({s['toAdmin']})   {s['distance']:.4f}")
        print("    새로 : " + " · ".join(s["arrived"]))
        print("    사라짐: " + " · ".join(s["left"]))

    if a.json:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({
            "meta": {
                "years": years, "yearAdmin": {str(y): admin_of[y] for y in years},
                "skipped": sorted(SKIP_YEARS), "vocabSize": len(vocab),
                "insideMean": round(mi, 4), "acrossMean": round(ma, 4),
                "ratio": round(ma / mi, 2),
            },
            "steps": steps,
        }, ensure_ascii=False), encoding="utf-8")
        print(f"\n→ {OUT}  ({OUT.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
