"""절 제목 931개를 **줄기** 로 묶는다. 기능 2의 ① 주제 흐름이 쓸 재료다.

    python scripts/themes.py            표로 본다
    python scripts/themes.py --unmatched 어디에도 안 붙은 제목을 본다
    python scripts/themes.py --json     web/theme-data.json 으로 내보낸다

**왜 묶나.** 백서는 같은 일을 해마다 다르게 부른다.

    2011  소프트 파워를 활용한 공공외교 강화
    2018  통합적·체계적 공공외교 추진
    2022  글로벌 가치에 기여하는 맞춤형 공공외교 강화
    2025  K-이니셔티브 실현을 위한 공공외교 강화

말은 넷이지만 하는 일은 하나다. 묶어야 37년이 강물처럼 흐른다.

**줄기 이름은 우리가 짓지 않았다.** 절 제목 931개에 실제로 쓰인 말을 세어
많이 나온 것부터 골랐다(`외교` 149회 · `지역` 78 · `경제` 27 · `재외국민` 24 …).
붙이는 열쇠말도 백서가 쓴 말이다.

**분류율을 반드시 함께 밝힌다.** 어디에도 안 붙은 절이 몇 개인지 세어
표 아래에 적는다. 안 붙은 것을 숨기면 흐름 그림이 실제보다 깔끔해 보인다.
"""

import argparse
import io
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX = PROJECT_ROOT / "corpus" / "index.jsonl"
OUT = PROJECT_ROOT / "web" / "theme-data.json"

# 줄기. 순서가 곧 **우선순위**다 — 앞의 것이 먼저 가져간다.
# 한 절에 '한반도'와 '지역'이 같이 있으면 한반도로 간다. 더 좁은 것이 앞이다.
#
# 열쇠말은 전부 절 제목에 실제로 나온 말이다. 지어낸 말은 없다.
THEMES = [
    ("코로나·보건", "#111318", [
        "코로나", "감염병", "방역", "백신", "보건", "생명과 안전", "기업 애로",
    ]),
    ("한반도·북핵", "#b23a2e", [
        "한반도", "북핵", "북한", "남북", "통일", "평화정착", "평화체제", "비핵화",
        "핵문제", "6자", "육자", "개성", "이산가족", "평화증진", "평화 구현",
        "平和統一", "平和 統一", "대북", "화해", "평화번영", "韓半島", "韓牛島",
        "韓持鳥", "韓盾島",
    ]),
    ("개발협력", "#7fa8e0", [
        "개발협력", "ODA", "공적개발", "개도국", "개발도상", "국제개발", "기여 강화",
        "開發途上",
    ]),
    ("영사·재외국민", "#5fc7bd", [
        "재외국민", "영사", "동포", "해외진출", "편익", "국민보호", "재외동포",
        "해외 체류", "여권", "在外國民", "領事", "海外進出", "교포", "해외여행",
        "國民生", "삐트의",
    ]),
    ("공공·문화외교", "#cf8ab6", [
        "공공외교", "문화", "홍보", "국가이미지", "브랜드", "학술", "체육", "청소년",
        "소프트", "文化", "學術", "體育", "弘報", "홍보활동", "대국민 접촉",
    ]),
    ("법적기반", "#6f6a9c", [
        "법적", "국제법", "조약", "협정 체결", "대외관계", "대외 관계", "國際法",
    ]),
    ("외교인프라", "#a9a396", [
        "조직", "인사", "교육", "연구", "역량", "업무", "혁신", "인프라", "수행 체제",
        "정보화", "예산", "外務部",
    ]),
    ("경제·통상", "#2f7d5e", [
        "경제", "통상", "FTA", "자유무역", "무역", "투자", "에너지", "자원", "공급망",
        "경제안보", "과학기술", "기후", "환경", "북극", "녹색", "저탄소", "금융",
        "經濟", "通商", "산업", "WTO", "OECD", "DDA", "도하", "수입규제", "일자리",
    ]),
    ("다자·국제기구", "#3a5a8f", [
        "다자", "유엔", "국제기구", "범세계", "국제평화", "안보", "군축", "비확산",
        "원자력", "제재", "수출통제", "인권", "민주주의", "국제사회", "소다자",
        "중견국", "지역협의체", "협의체", "國際機構", "非同盟", "APEC", "국제무대",
        "태평양협력", "국제협력", "연대",
    ]),
    ("주변국·동맹", "#e0955f", [
        "한미", "한·미", "한･미", "동맹", "주변국", "동북아", "한일", "한·일", "한･일",
        "한중", "한·중", "한러", "한·러", "우방", "友邦", "4국", "주요국",
        "북방외교", "北方外交", "정상외교", "고위급", "전방위",
    ]),
    ("지역외교", "#9c7b1f", [
        "지역", "아시아", "아태", "아·태", "아세안", "유럽", "구주", "미주", "북미",
        "중남미", "아프리카", "중동", "대양주", "남아시아", "중앙아시아", "신남방",
        "신북방", "인도-태평양", "인태", "지역별", "地域", "亞", "歐", "美", "다변화",
    ]),
    ("국민과 함께", "#8f6f3a", [
        "국민 참여", "국민적", "국민외교", "소통", "지지 확보", "국민이 체감",
        "국민과", "汎國民", "의원외교", "議員外交",
    ]),
    ("국제정세", "#57524a", [
        "정세", "기조", "개관", "국제질서", "동향", "情勢", "秩序", "施策", "外交政策",
        "외교시책", "외교 시책", "정책 목표", "정책목표", "주요정책", "개 _ 관",
    ]),
]


def load() -> list[dict]:
    if not INDEX.exists():
        raise SystemExit(f"[ERROR] {INDEX} 가 없다. scripts/index.py --write 를 먼저 돌린다.")
    rows = [json.loads(l) for l in INDEX.open(encoding="utf-8")]
    return [r for r in rows if r["절"] is not None and r["절제목"]]


# 기관 이름은 주제가 아니다. **'외교통상부 기본 혁신 방향'** 이 이름 속
# '통상' 때문에 경제·통상으로 갔다(2026-08-16 표본 검사에서 잡았다).
# 이름을 먼저 걷어내고 주제를 찾는다.
_ORG = re.compile(r"외교통상부|통상교섭본부|외교부|외무부|外交通商部|外務部")


def classify(title: str) -> str | None:
    """제목 하나를 줄기 하나에 붙인다. 어디에도 안 붙으면 None."""
    t = _ORG.sub("", re.sub(r"\s+", "", title))
    for name, _, keys in THEMES:
        for k in keys:
            if re.sub(r"\s+", "", k) in t:
                return name
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unmatched", action="store_true", help="안 붙은 제목을 본다")
    ap.add_argument("--json", action="store_true", help="web/theme-data.json 으로 내보낸다")
    a = ap.parse_args()

    secs = load()
    hit, miss = [], []
    for r in secs:
        th = classify(r["절제목"])
        (hit if th else miss).append({**r, "줄기": th})

    if a.unmatched:
        print(f"어디에도 안 붙은 절 {len(miss)}개\n")
        for r in sorted(miss, key=lambda r: r["연도"]):
            print(f"  {r['연도']}  제{r['장']}장 제{r['절']}절  {r['절제목']}")
        return

    years = sorted({r["연도"] for r in secs})
    admin = {r["연도"]: r["정권"] for r in secs}
    per = defaultdict(Counter)              # 연도 → 줄기 → 절 수
    for r in hit:
        per[r["연도"]][r["줄기"]] += 1

    names = [n for n, _, _ in THEMES]
    print(f"절 {len(secs)}개 · 줄기 {len(names)}개 · "
          f"붙은 것 {len(hit)}개 ({100*len(hit)/len(secs):.1f}%) · 안 붙은 것 {len(miss)}개\n")
    print(f"{'줄기':<14}{'절':>5}{'연도':>5}  처음~끝")
    print("-" * 46)
    for n in names:
        rs = [r for r in hit if r["줄기"] == n]
        ys = sorted({r["연도"] for r in rs})
        span = f"{ys[0]}~{ys[-1]}" if ys else "—"
        print(f"{n:<14}{len(rs):>5}{len(ys):>5}  {span}")
    print("-" * 46)
    print(f"{'안 붙음':<14}{len(miss):>5}")

    if a.json:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({
            "meta": {
                "years": years,
                "yearAdmin": {str(y): admin[y] for y in years},
                "themes": [{"name": n, "color": c} for n, c, _ in THEMES],
                "sections": len(secs), "matched": len(hit), "unmatched": len(miss),
                "matchRate": round(100 * len(hit) / len(secs), 1),
            },
            "byYear": {str(y): dict(per[y]) for y in years},
            "sections": [{"연도": r["연도"], "장": r["장"], "절": r["절"],
                          "제목": r["절제목"], "줄기": r["줄기"], "출처": r["출처"]}
                         for r in hit],
            "unmatched": [{"연도": r["연도"], "제목": r["절제목"]} for r in miss],
        }, ensure_ascii=False), encoding="utf-8")
        print(f"\n→ {OUT}  ({OUT.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    main()
