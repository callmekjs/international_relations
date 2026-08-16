"""문장에서 나라·정책·사건·조약을 뽑고, 함께 나온 것끼리 이어 관계에 종류를 붙인다.

지식그래프의 재료를 만든다. 다섯 종류를 한 판에 올린다.

    🌍 나라·기구   사전을 놓고 찾는다 — '미국'은 언제나 미국이다
    📋 정책        말의 생김새로 찾고, **정권 편중도**로 진짜 이름만 남긴다
    ⚡ 사건        사태·전쟁·위기·실험 …
    📜 조약        협정·조약·협약 … 사건과 성질이 달라 따로 둔다

숫자는 하나도 지어내지 않는다. 전부 corpus/sentences.jsonl 을 세어서 나온다.
사전에 적는 것은 나라·기구 **이름**뿐이고, 정책·사건 이름은 데이터가 정한다.

    python scripts/mine_entities.py
    → web/graph-data.json
"""

import io
import json
import math
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
# 이름만 적는다. 몇 번 나오는지·무엇과 이어지는지는 데이터가 답한다.
COUNTRIES = {
    "미국": ["미국", "美國", "미합중국"], "중국": ["중국", "中國", "중화인민공화국"],
    "일본": ["일본", "日本"], "러시아": ["러시아", "소련", "蘇聯"],
    "북한": ["북한", "北韓", "조선민주주의인민공화국"],
    "베트남": ["베트남"], "인도네시아": ["인도네시아"], "인도": ["인도"],
    "필리핀": ["필리핀"], "태국": ["태국"], "싱가포르": ["싱가포르"],
    "말레이시아": ["말레이시아"], "미얀마": ["미얀마", "버마"], "캄보디아": ["캄보디아"],
    "라오스": ["라오스"], "대만": ["대만", "臺灣", "타이완"], "몽골": ["몽골"],
    "호주": ["호주", "오스트레일리아"], "뉴질랜드": ["뉴질랜드"],
    "카자흐스탄": ["카자흐스탄"], "우즈베키스탄": ["우즈베키스탄"],
    "독일": ["독일", "獨逸", "서독", "동독"], "프랑스": ["프랑스"], "영국": ["영국", "英國"],
    "이탈리아": ["이탈리아"], "스페인": ["스페인"], "네덜란드": ["네덜란드"],
    "폴란드": ["폴란드"], "터키": ["터키", "튀르키예"], "우크라이나": ["우크라이나"],
    "이란": ["이란"], "이라크": ["이라크"], "사우디아라비아": ["사우디아라비아", "사우디"],
    "아랍에미리트": ["아랍에미리트", "UAE"], "이스라엘": ["이스라엘"], "이집트": ["이집트"],
    "남아프리카공화국": ["남아프리카공화국", "남아공"], "나이지리아": ["나이지리아"],
    "에티오피아": ["에티오피아"], "케냐": ["케냐"],
    "브라질": ["브라질"], "멕시코": ["멕시코"], "아르헨티나": ["아르헨티나"],
    "칠레": ["칠레"], "콜롬비아": ["콜롬비아"], "캐나다": ["캐나다"],
    "파키스탄": ["파키스탄"], "방글라데시": ["방글라데시"], "스리랑카": ["스리랑카"],
    "네팔": ["네팔"],
}
ORGS = {
    "유엔": ["유엔", "UN", "국제연합"], "아세안": ["아세안", "ASEAN"],
    "유럽연합": ["유럽연합", "EU"], "APEC": ["APEC", "아시아태평양경제협력체"],
    "OECD": ["OECD", "경제협력개발기구"], "WTO": ["WTO", "세계무역기구"],
    "IAEA": ["IAEA", "국제원자력기구"], "NATO": ["NATO", "나토", "북대서양조약기구"],
    "G20": ["G20"], "IMF": ["IMF", "국제통화기금"], "WHO": ["WHO", "세계보건기구"],
    "ARF": ["ARF", "아세안지역안보포럼"],
}

# ── 정책·사건·조약은 '말의 생김새'로 찾는다 ──────────────────────────────────
# 사전을 만들 수 없다. 어떤 정책이 있었는지 미리 알 수 없기 때문이다.
# 대신 국문 공문서가 그것들을 부르는 **꼴**이 정해져 있다는 점을 쓴다.
_TAIL = {
    "policy": "정책|구상|이니셔티브|전략|독트린|플랜|비전",
    "event":  "사태|사건|전쟁|분쟁|위기|실험|도발|피격|참사|쿠데타",
    "treaty": "협정|조약|협약|의정서|공동선언|합의서",
}
# 두 벌을 쓴다. 하나로 합치면 되돌이(backtracking)가 폭발한다(2026-08-15 교훈).
#   ① 붙여 쓴 것    '신남방정책'
#   ② 한 칸 띄운 것 '담대한 구상'  ← 이걸 놓쳐 윤석열 정부 대북정책이 통째로 빠졌다
_PAT = {}
for _kind, _tail in _TAIL.items():
    _PAT[_kind] = (
        re.compile(rf"(?<![가-힣])([가-힣A-Za-z0-9·]{{2,12}}?(?:{_tail}))(?![가-힣])"),
        re.compile(rf"(?<![가-힣])([가-힣]{{2,6}}\s(?:{_tail}))(?![가-힣])"),
    )

# 조사를 뗀다. 안 떼면 '신남방정책'과 '신남방정책을'이 따로 세어져 절반을 잃는다
# (2026-08-16 실측: 162회 중 82회만 잡혔다).
_JOSA = re.compile(r"(?:을|를|의|에|와|과|은|는|이|가|으로|로|에서|에게|까지|부터|도|만|"
                   r"이라는|라는|이라고|라고|이나|나|보다|처럼|이며|며|인|적)$")

# 영문 병기 — '확산방지구상(Proliferation Security Initiative)' 처럼.
# 진짜 정책 이름에만 따라붙는다. 정권 편중도로 못 잡는 것을 이게 건진다.
# 나라 이름처럼 보이지만 아닌 것. 지역 이름·복합어에 갇힌 글자다.
_REGION_NOISE = re.compile(r"인도[-‐‑–—ㆍ·]?\s?태평양|인태")

_ENG = re.compile(r"[（(]\s*[A-Za-z][A-Za-z0-9 ,.\-&/']{4,60}[)）]")

# ── 관계에 종류 붙이기 ───────────────────────────────────────────────────────
# **욕심내지 않는다.** 확실한 것만 붙이고 애매하면 '언급'으로 둔다.
# 다 붙이고 반이 틀리는 것보다, 절반만 붙이고 그게 맞는 편이 낫다.
_REL = {
    "협력": r"협력|공조|증진|강화|체결|확대|파트너|동반자|우호|친선|교류|지지|합의",
    "갈등": r"제재|규탄|항의|우려|비판|도발|위협|반대|철회|침공|긴장|억류|납치",
    "대화": r"회담|협의|방문|면담|접견|대화|교섭|순방|정상회의",
    "지원": r"지원|공여|원조|파견|기여|무상|차관|구호",
}
_REL_PAT = {k: re.compile(v) for k, v in _REL.items()}

MIN_YEARS = 2
# 관계로 인정할 최소 동시 등장 횟수. **종류마다 다르다.**
# 나라끼리는 원래 자주 함께 나오므로 8회쯤은 흔하다. 그러나 정책·사건·조약은
# 언급 자체가 드물어서(인태전략 32회) 8회를 요구하면 선이 하나도 안 남는다.
# 2026-08-16 에 실제로 93개 점 중 18개가 선을 잃고 화면에서 사라졌다.
MIN_EDGE = 8
MIN_EDGE_RARE = 3
_DENSE = {"country", "org"}
MIN_MENTIONS = {"country": 25, "org": 25, "policy": 10, "event": 12, "treaty": 15}
TOP_PER_KIND = {"country": 45, "org": 12, "policy": 40, "event": 40, "treaty": 30}
# 진짜 이름인지 가르는 문턱. 2026-08-16 실측으로 정했다.
#   진짜 이름  신남방정책 100% · 인태전략 100% · 동북아평화협력구상 98% · 포용정책 94%
#   보통명사   대북정책 48% · 통상정책 40% · 대외정책 30% · 외교정책 18%
# 94% 위와 48% 아래 사이에 아무것도 없다. 0.9 를 문턱으로 삼는다.
ADMIN_FOCUS_MIN = 0.90
# 사건·조약은 시간 집중도로 가른다(가장 많은 3개 해가 전체의 몇 %인가).
TIME_FOCUS_MIN = 0.50
# 편중도로 못 잡는 것을 영문 병기가 건진다(확산방지구상 편중 33%, 영문 13회).
ENG_MIN = 5
# 횟수만 보면 안 된다. 521번 나오는 '외교정책'은 어쩌다 5번쯤 영문과 만난다.
# **비율**을 함께 본다 — 진짜 이름은 나올 때마다 영문이 따라붙는다.
ENG_RATIO_MIN = 0.10
# 관계 종류를 붙일 조건. 과반이 한 쪽이고, 그 근거가 세 문장 이상일 때만.
REL_CONF_MIN = 0.60
REL_COUNT_MIN = 3


def build_alias_map(groups: dict) -> list[tuple[str, str]]:
    """긴 이름부터 찾도록 정렬한다 — '인도네시아'를 '인도'로 잘못 세지 않게."""
    pairs = [(n, canon) for canon, names in groups.items() for n in names]
    pairs.sort(key=lambda p: -len(p[0]))
    return pairs


def strip_josa(w: str) -> str:
    w = w.strip()
    prev = None
    while w != prev and len(w) > 3:      # 두 번까지 ('…책을' → '…책')
        prev = w
        w = _JOSA.sub("", w)
    return w


# 이름의 첫머리가 될 수 없는 말. 문장 조각이 이름으로 둔갑하는 것을 막는다
# ('관한 협약', '계기 정상회담', '외교부는 사건' 같은 것이 잡혔다).
_NOT_HEAD = re.compile(r"^(관한|계기|대한|따른|위한|통한|의한|대통령과|외교부는|해외|"
                       r"각종|여러|기타|일부|주요|국제|양국|해당|이러한|그러한|다양한)|"
                       r"^[가-힣]{1,3}(는|은|이|가|을|를|와|과|의|에)\s")


def find_named(text: str, kind: str) -> set[str]:
    out = set()
    for pat in _PAT[kind]:
        for m in pat.finditer(text):
            w = strip_josa(re.sub(r"\s+", " ", m.group(1)))
            if len(w) < 4 or _NOT_HEAD.search(w):
                continue
            out.add(w)
    return out


def canon_name(w: str) -> str:
    """'테러 사태'와 '테러사태'는 같은 것이다. 공백을 떼어 하나로 모은다.
    안 그러면 113회와 22회로 갈려 둘 다 약해 보인다."""
    return w.replace(" ", "")


# 두 개체 사이를 얼마나 넓게 볼지(글자). 국문은 서술어가 뒤에 오므로
# 뒤쪽을 넉넉히 준다.
SPAN_BACK = 10
SPAN_FWD = 45


# 한 문장에 개체가 이만큼 넘게 나오면 '나열'로 본다.
#   "미국, 일본, 중국, 러시아, 호주, 인도, 브라질 등 25여개국과 조약을 체결"
# 이런 문장은 한국이 **각각과** 맺은 관계를 적은 것이지, 그 나라들끼리
# 협력했다는 뜻이 아니다. 그런데 짝을 다 이으면 '중국—브라질 협력'이 생긴다.
# 2026-08-16 표본 24개를 손으로 본 결과, 틀린 라벨 12개 중 9개가 이것이었다.
MAX_ENTITIES_FOR_REL = 4
# 두 이름이 이보다 멀면 같은 이야기가 아니다.
MAX_SPAN_CHARS = 120
# 나열 표시. 이게 두 이름 사이에 있으면 '나란히 적힌 것'이지 '서로 관계'가 아니다.
_LIST_MARK = re.compile(r"[,、·ㆍ]|및|등")


def relation_between(text: str, a: str, b: str, others: set[str]) -> str | None:
    """a 와 b **사이 구간**에서 관계를 읽는다.

    문장 전체를 보면 안 된다. 2026-08-16 실측:
        "중국의 사태가 발생하고 일본의 정국이 극히 유동적으로 진행되어…"
    이 문장에 '협력'이 어딘가 있다는 이유로 미국—일본이 '협력'으로 붙었다.
    관계는 **두 이름 사이에 쓰인 말**이 정한다.

    그리고 **하나만 딱 맞을 때만** 답한다. 둘 이상 걸리면 무엇인지 알 수 없다."""
    ia, ib = text.find(a), text.find(b)
    if ia < 0 or ib < 0:
        return None
    lo, hi = (ia + len(a), ib) if ia < ib else (ib + len(b), ia)
    if hi - lo > MAX_SPAN_CHARS:
        return None
    between = text[lo:hi]
    # 사이에 **다른 개체**가 끼어 있으면 나열이다. 이웃한 두 이름만 잇는다.
    if any(o in between for o in others):
        return None
    # 쉼표·가운뎃점·'및'·'등'이 사이에 있으면 그것도 나열이다.
    #   "아르헨티나, 【호주】, 【중국】과는 상용 복수사증협정체결을 추진"
    # 한국이 각각과 맺은 것이지 호주—중국의 관계가 아니다.
    if _LIST_MARK.search(between):
        return None
    span = text[max(0, lo - SPAN_BACK): hi + SPAN_FWD]
    hits = [k for k, pat in _REL_PAT.items() if pat.search(span)]
    return hits[0] if len(hits) == 1 else None


def main() -> None:
    if not CORPUS.exists():
        raise SystemExit(f"[ERROR] {CORPUS} 가 없다. corpus.py 를 먼저 돌린다.")

    country_alias = build_alias_map(COUNTRIES)
    org_alias = build_alias_map(ORGS)

    mentions: dict[str, Counter] = defaultdict(Counter)
    kind_of: dict[str, str] = {}
    admin_of: dict[str, Counter] = defaultdict(Counter)
    eng_of: Counter = Counter()
    edges: Counter = Counter()
    edge_years: dict[tuple, Counter] = defaultdict(Counter)
    edge_kinds: dict[tuple, Counter] = defaultdict(Counter)
    edge_sample: dict[tuple, dict] = {}
    sample_of: dict[str, tuple] = {}
    year_admin: dict[int, str] = {}
    sent_per_year: Counter = Counter()
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
            sent_per_year[year] += 1

            found: set[str] = set()
            # '인도-태평양'은 지역 이름이지 인도(India)가 아니다. 먼저 지운다.
            # 2026-08-16 표본에서 '인도—인태전략', '영국—인도' 같은 헛 관계가
            # 전부 여기서 나왔다.
            rest = _REGION_NOISE.sub(" ", text)
            # 찾은 이름은 지우면서 간다 — '인도네시아' 한 번에 '인도'까지 세지 않게
            for alias, canon in country_alias:
                if alias in rest:
                    found.add(canon); kind_of[canon] = "country"
                    rest = rest.replace(alias, "\x00")
            for alias, canon in org_alias:
                if alias in rest:
                    found.add(canon); kind_of[canon] = "org"
                    rest = rest.replace(alias, "\x00")
            for kind in ("policy", "event", "treaty"):
                for w0 in find_named(text, kind):
                    w = canon_name(w0)
                    found.add(w); kind_of[w] = kind
                    i = text.find(w0) + len(w0)
                    if _ENG.search(text[i:i + 70]):
                        eng_of[w] += 1

            for name in found:
                mentions[name][year] += 1
                admin_of[name][admin] += 1
                if name not in sample_of and 40 < len(text) < 220:
                    sample_of[name] = (year, admin, text)

            ordered = sorted(found)
            for i, a in enumerate(ordered):
                for b in ordered[i + 1:]:
                    key = (a, b)
                    edges[key] += 1
                    edge_years[key][year] += 1
                    rk = (relation_between(text, a, b, found - {a, b})
                          if len(found) <= MAX_ENTITIES_FOR_REL else None)
                    if rk:
                        edge_kinds[key][rk] += 1
                        # 샘플은 **그 라벨을 뒷받침하는 문장**이어야 한다.
                        # 아무 문장이나 두면 "왜 협력이죠?"에 답할 수 없다.
                        if len(text) < 220:
                            edge_sample.setdefault(key, {}).setdefault(
                                rk, {"year": year, "text": text})

    print(f"  문장 {n_sent:,}개 · 후보 개체 {len(mentions):,}개")

    # ── 개체 고르기 ──────────────────────────────────────────────────────────
    kept: dict[str, str] = {}
    dropped_generic = []
    by_kind: dict[str, list] = defaultdict(list)
    for name, cnt in mentions.items():
        kind = kind_of[name]
        total = sum(cnt.values())
        if total < MIN_MENTIONS.get(kind, 25) or len(cnt) < MIN_YEARS:
            continue
        if kind == "policy":
            # 정책은 **한 정부가 만든 이름**이다. 그래서 한 정권에만 나온다.
            #   신남방정책 100% · 인태전략 100% · 포용정책 94%
            #   대북정책 48% · 통상정책 40% · 외교정책 18%  ← 아무 정부나 쓰는 말
            c = admin_of[name]
            focus = max(c.values()) / sum(c.values())
            eng_ratio = eng_of[name] / total
            if focus < ADMIN_FOCUS_MIN and (eng_of[name] < ENG_MIN or eng_ratio < ENG_RATIO_MIN):
                dropped_generic.append((total, name, round(focus, 2), eng_of[name]))
                continue
        elif kind in ("event", "treaty"):
            # 사건·조약에는 정권 잣대를 쓰면 안 된다. 남북정상회담처럼 여러 정권에
            # 걸쳐 되풀이되는 것이 있기 때문이다(2026-08-16 에 이걸로 잘못 뺐다).
            # 대신 **시간 집중도**를 본다 — 진짜 사건은 몇 해에 몰린다.
            #   테러사태 100% · 포격도발 89% · 남북정상회담 88% · 천안문사태 70%
            #   항공협정 24% · 다자조약 23% · 공동선언 22%  ← 종류 이름일 뿐
            v = sorted(cnt.values(), reverse=True)
            focus = sum(v[:3]) / total
            eng_ratio = eng_of[name] / total
            if focus < TIME_FOCUS_MIN and (eng_of[name] < ENG_MIN or eng_ratio < ENG_RATIO_MIN):
                dropped_generic.append((total, name, round(focus, 2), eng_of[name]))
                continue
        by_kind[kind].append((total, name))
    for kind, items in by_kind.items():
        items.sort(reverse=True)
        for total, name in items[:TOP_PER_KIND.get(kind, 40)]:
            kept[name] = kind
    print("  남긴 개체: " + " · ".join(
        f"{k} {sum(1 for v in kept.values() if v == k)}개"
        for k in ("country", "org", "policy", "event", "treaty")))
    dropped_generic.sort(reverse=True)
    print(f"  보통명사로 보고 뺀 것 {len(dropped_generic)}개: "
          + " · ".join(n for _, n, _, _ in dropped_generic[:8]))

    # ── 점 ──────────────────────────────────────────────────────────────────
    nodes = []
    for name, kind in sorted(kept.items(), key=lambda x: -sum(mentions[x[0]].values())):
        cnt = mentions[name]
        # **분량 보정.** 해마다 백서 두께가 다르다(2004년 276문장, 2012년 2,080문장).
        # 그대로 세면 '그 해 백서가 두꺼웠나'를 재는 셈이 된다.
        rate = {str(y): round(c / sent_per_year[y] * 10000, 1) for y, c in sorted(cnt.items())}
        s = sample_of.get(name)
        adm = admin_of[name]
        nodes.append({
            "id": name, "kind": kind,
            "total": sum(cnt.values()),
            "byYear": {str(y): c for y, c in sorted(cnt.items())},
            "rateByYear": rate,
            "byAdmin": dict(adm.most_common()),
            "focus": round(max(adm.values()) / sum(adm.values()), 2),
            "first": min(cnt), "last": max(cnt),
            "peak": max(cnt, key=cnt.get),
            "peakRate": max(rate, key=rate.get),
            "sample": {"year": s[0], "admin": s[1], "text": s[2]} if s else None,
        })

    # ── 선 ──────────────────────────────────────────────────────────────────
    total_of = {n["id"]: n["total"] for n in nodes}
    links = []
    for (a, b), w in edges.items():
        if a not in kept or b not in kept:
            continue
        bar = MIN_EDGE if (kept[a] in _DENSE and kept[b] in _DENSE) else MIN_EDGE_RARE
        if w < bar:
            continue
        # 관계 강도 두 가지.
        #   weight  그냥 몇 번 함께 나왔나 — 흔한 것끼리 무조건 커진다
        #   pmi     '우연보다 얼마나 자주 함께 나오나' — 특별한 관계가 드러난다
        #           (라오스—캄보디아, 브라질—아르헨티나 같은 것)
        pmi = math.log(w * n_sent / (total_of[a] * total_of[b]))
        ks = edge_kinds[(a, b)]
        rel, conf = None, 0.0
        if ks:
            top, c = ks.most_common(1)[0]
            share = c / sum(ks.values())
            if share >= REL_CONF_MIN and c >= REL_COUNT_MIN:
                rel, conf = top, round(share, 2)
        links.append({
            "source": a, "target": b, "weight": w, "pmi": round(pmi, 2),
            "rel": rel, "relConf": conf,
            "relCounts": dict(ks.most_common()) if ks else {},
            "byYear": {str(y): c for y, c in sorted(edge_years[(a, b)].items())},
            "sample": (edge_sample.get((a, b), {}).get(rel) if rel else None),
        })
    links.sort(key=lambda e: -e["weight"])
    labeled = sum(1 for l in links if l["rel"])
    print(f"  관계 {len(links):,}개 · 종류가 붙은 것 {labeled:,}개 "
          f"({labeled/max(len(links),1)*100:.0f}%)")

    gaps = {}
    for y in sorted(year_admin):
        m = PROJECT_ROOT / "etl_test" / str(y) / "meta.json"
        if m.exists():
            g = json.loads(m.read_text(encoding="utf-8")).get("knownGaps", [])
            if g:
                gaps[str(y)] = g

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "meta": {
            "gaps": gaps, "sentences": n_sent,
            "sentPerYear": {str(y): c for y, c in sorted(sent_per_year.items())},
            "years": sorted(year_admin),
            "yearAdmin": {str(y): a for y, a in sorted(year_admin.items())},
            "relKinds": list(_REL),
        },
        "nodes": nodes, "links": links,
    }, ensure_ascii=False), encoding="utf-8")
    print(f"→ {OUT}  ({OUT.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
