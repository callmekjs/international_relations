"""문장에서 나라·정책·사건을 뽑고, 한 문장 안에 함께 나온 것끼리 이어 준다.

지식그래프의 재료를 만든다. 세 종류를 한 판에 올린다.

    🌍 나라·기구   사전을 놓고 찾는다 — '미국'은 언제나 미국이다
    📋 정책        말의 생김새로 찾는다 — '○○정책/구상/외교/전략'
    ⚡ 사건        말의 생김새로 찾는다 — '○○사태/사건/전쟁/실험/위기'

숫자는 하나도 지어내지 않는다. 전부 corpus/sentences.jsonl 을 세어서 나온다.
사전에 적는 것은 **이름**뿐이고, 얼마나 나오는지·무엇과 이어지는지는 데이터가 정한다.

    python scripts/mine_entities.py
    → web/graph-data.json
"""

import io
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORPUS = PROJECT_ROOT / "corpus" / "sentences.jsonl"
OUT = PROJECT_ROOT / "web" / "graph-data.json"

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 나라·기구 사전 ───────────────────────────────────────────────────────────
# 이름만 적는다. 백서에 실제로 몇 번 나오는지, 무엇과 함께 나오는지는 데이터가 답한다.
# 표기가 여럿인 것은 대표 이름 하나로 모은다(한·미 → 미국).
COUNTRIES = {
    "미국": ["미국", "美國", "미합중국"],
    "중국": ["중국", "中國", "중화인민공화국"],
    "일본": ["일본", "日本"],
    "러시아": ["러시아", "소련", "蘇聯", "露西亞"],
    "북한": ["북한", "北韓", "조선민주주의인민공화국"],
    "베트남": ["베트남", "越南"],
    "인도": ["인도네시아우선", "인도"],          # '인도네시아' 오탐 방지용 순서
    "인도네시아": ["인도네시아"],
    "필리핀": ["필리핀"],
    "태국": ["태국", "泰國"],
    "싱가포르": ["싱가포르"],
    "말레이시아": ["말레이시아"],
    "미얀마": ["미얀마", "버마"],
    "호주": ["호주", "오스트레일리아"],
    "뉴질랜드": ["뉴질랜드"],
    "몽골": ["몽골"],
    "카자흐스탄": ["카자흐스탄"],
    "우즈베키스탄": ["우즈베키스탄"],
    "독일": ["독일", "獨逸", "서독", "동독"],
    "프랑스": ["프랑스", "佛蘭西"],
    "영국": ["영국", "英國"],
    "이탈리아": ["이탈리아"],
    "스페인": ["스페인"],
    "네덜란드": ["네덜란드"],
    "폴란드": ["폴란드"],
    "터키": ["터키", "튀르키예"],
    "우크라이나": ["우크라이나"],
    "이란": ["이란", "伊朗"],
    "이라크": ["이라크"],
    "사우디아라비아": ["사우디아라비아", "사우디"],
    "아랍에미리트": ["아랍에미리트", "UAE"],
    "이스라엘": ["이스라엘"],
    "이집트": ["이집트"],
    "남아프리카공화국": ["남아프리카공화국", "남아공"],
    "나이지리아": ["나이지리아"],
    "에티오피아": ["에티오피아"],
    "케냐": ["케냐"],
    "브라질": ["브라질"],
    "멕시코": ["멕시코"],
    "아르헨티나": ["아르헨티나"],
    "칠레": ["칠레"],
    "콜롬비아": ["콜롬비아"],
    "캐나다": ["캐나다"],
    "파키스탄": ["파키스탄"],
    "방글라데시": ["방글라데시"],
    "스리랑카": ["스리랑카"],
    "네팔": ["네팔"],
    "캄보디아": ["캄보디아"],
    "라오스": ["라오스"],
    "대만": ["대만", "臺灣", "타이완"],
}
ORGS = {
    "유엔": ["유엔", "UN", "국제연합", "國際聯合"],
    "아세안": ["아세안", "ASEAN"],
    "유럽연합": ["유럽연합", "EU"],
    "APEC": ["APEC", "아시아태평양경제협력체"],
    "OECD": ["OECD", "경제협력개발기구"],
    "WTO": ["WTO", "세계무역기구"],
    "IAEA": ["IAEA", "국제원자력기구"],
    "NATO": ["NATO", "나토", "북대서양조약기구"],
    "G20": ["G20"],
    "IMF": ["IMF", "국제통화기금"],
    "WHO": ["WHO", "세계보건기구"],
    "ARF": ["ARF", "아세안지역안보포럼"],
}

# ── 정책·사건은 '말의 생김새'로 찾는다 ────────────────────────────────────────
# 사전을 만들 수 없다. 어떤 정책이 있었는지 우리가 미리 알 수 없기 때문이다.
# 대신 국문 공문서가 정책·사건을 부르는 **꼴**이 정해져 있다는 점을 쓴다.
_POLICY = re.compile(
    r"(?<![가-힣])([가-힣A-Za-z0-9·]{2,12}?"
    r"(?:정책|구상|이니셔티브|전략|독트린|플랜|비전))(?![가-힣])")
_EVENT = re.compile(
    r"(?<![가-힣])([가-힣A-Za-z0-9·]{2,12}?"
    r"(?:사태|사건|전쟁|분쟁|위기|실험|도발|테러|피격|사고|정상회담|협정|조약|선언))(?![가-힣])")

# 너무 흔해서 이름 구실을 못 하는 것들 — 데이터를 보고 걸러낼 기준
MIN_YEARS = 2            # 한 해만 반짝한 것은 뺀다(오탐이 많다)
MIN_EDGE = 8             # 이만큼 함께 나와야 '관계'로 본다
# 몇 번 나와야 '개체'로 볼지. 나라는 흔하고 정책 이름은 드물어서 잣대가 다르다.
MIN_MENTIONS = {"country": 25, "org": 25, "policy": 10, "event": 15}
TOP_PER_KIND = {"country": 45, "org": 12, "policy": 60, "event": 60}


def build_alias_map(groups: dict) -> list[tuple[str, str]]:
    """긴 이름부터 찾도록 정렬한다 — '인도네시아'를 '인도'로 잘못 세지 않게."""
    pairs = []
    for canon, names in groups.items():
        for n in names:
            if n.endswith("우선"):      # 자리 맞추기용 더미
                continue
            pairs.append((n, canon))
    pairs.sort(key=lambda p: -len(p[0]))
    return pairs


def main() -> None:
    if not CORPUS.exists():
        raise SystemExit(f"[ERROR] {CORPUS} 가 없다. corpus.py 를 먼저 돌린다.")

    country_alias = build_alias_map(COUNTRIES)
    org_alias = build_alias_map(ORGS)

    mentions: dict[str, Counter] = defaultdict(Counter)      # 이름 → 연도별 횟수
    kind_of: dict[str, str] = {}
    years_of: dict[str, set] = defaultdict(set)
    admin_of: dict[str, Counter] = defaultdict(Counter)
    edges: Counter = Counter()                                # (a, b) → 함께 나온 문장 수
    edge_years: dict[tuple, Counter] = defaultdict(Counter)
    sample_of: dict[str, tuple] = {}
    year_admin: dict[int, str] = {}
    n_sent = 0

    print("문장을 읽는 중…")
    with CORPUS.open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("단위", "문장") != "문장":
                continue
            n_sent += 1
            text = r["한글"] or r["원문"]
            year, admin = r["연도"], r["정권"]
            year_admin[year] = admin

            found: set[str] = set()
            # **찾은 이름은 지우면서 간다.** 안 그러면 '인도네시아' 한 번에
            # '인도'까지 세어진다(2026-08-16 실측: 인도—인도네시아 637회라는
            # 있지도 않은 관계가 나왔다). 긴 이름부터 찾으므로 지우면 해결된다.
            rest = text
            for alias, canon in country_alias:
                if alias in rest:
                    found.add(canon); kind_of[canon] = "country"
                    rest = rest.replace(alias, "\x00")
            for alias, canon in org_alias:
                if alias in rest:
                    found.add(canon); kind_of[canon] = "org"
                    rest = rest.replace(alias, "\x00")
            for m in _POLICY.finditer(text):
                w = m.group(1); found.add(w); kind_of[w] = "policy"
            for m in _EVENT.finditer(text):
                w = m.group(1); found.add(w); kind_of[w] = "event"

            for name in found:
                mentions[name][year] += 1
                years_of[name].add(year)
                admin_of[name][admin] += 1
                if name not in sample_of and 40 < len(text) < 220:
                    sample_of[name] = (year, admin, text)

            ordered = sorted(found)
            for i, a in enumerate(ordered):
                for b in ordered[i + 1:]:
                    edges[(a, b)] += 1
                    edge_years[(a, b)][year] += 1

    print(f"  문장 {n_sent:,}개 · 후보 개체 {len(mentions):,}개")

    # 걸러내기 — 데이터가 정한 기준으로
    kept: dict[str, str] = {}
    by_kind: dict[str, list] = defaultdict(list)
    for name, cnt in mentions.items():
        total = sum(cnt.values())
        if total < MIN_MENTIONS.get(kind_of[name], 25) or len(years_of[name]) < MIN_YEARS:
            continue
        by_kind[kind_of[name]].append((total, name))
    for kind, items in by_kind.items():
        items.sort(reverse=True)
        for total, name in items[:TOP_PER_KIND.get(kind, 40)]:
            kept[name] = kind
    print("  남긴 개체: " + " · ".join(
        f"{k} {sum(1 for v in kept.values() if v == k)}개"
        for k in ("country", "org", "policy", "event")))

    nodes = []
    for name, kind in sorted(kept.items(), key=lambda x: -sum(mentions[x[0]].values())):
        cnt = mentions[name]
        y0, y1 = min(cnt), max(cnt)
        peak = max(cnt, key=cnt.get)
        s = sample_of.get(name)
        nodes.append({
            "id": name, "kind": kind,
            "total": sum(cnt.values()),
            "byYear": {str(y): c for y, c in sorted(cnt.items())},
            "byAdmin": dict(admin_of[name].most_common()),
            "first": y0, "last": y1, "peak": peak,
            "sample": {"year": s[0], "admin": s[1], "text": s[2]} if s else None,
        })

    links = []
    for (a, b), w in edges.items():
        if w < MIN_EDGE or a not in kept or b not in kept:
            continue
        links.append({"source": a, "target": b, "weight": w,
                      "byYear": {str(y): c for y, c in sorted(edge_years[(a, b)].items())}})
    links.sort(key=lambda e: -e["weight"])
    print(f"  관계 {len(links):,}개")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    gaps = {}
    for y in sorted(year_admin):
        m = PROJECT_ROOT / "etl_test" / str(y) / "meta.json"
        if m.exists():
            g = json.loads(m.read_text(encoding="utf-8")).get("knownGaps", [])
            if g:
                gaps[str(y)] = g

    OUT.write_text(json.dumps({
        "meta": {
            "gaps": gaps,
            "sentences": n_sent,
            "years": sorted(year_admin),
            "admins": [year_admin[y] for y in sorted(year_admin)],
            "yearAdmin": {str(y): a for y, a in sorted(year_admin.items())},
        },
        "nodes": nodes, "links": links,
    }, ensure_ascii=False), encoding="utf-8")
    print(f"→ {OUT}  ({OUT.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
