"""지식그래프가 얼마나 맞는지 잰다. 표본을 뽑아 근거 문장과 나란히 놓는다.

    python scripts/audit_graph.py            표본을 뽑아 보여준다
    python scripts/audit_graph.py --facts    아는 사실로 자동 채점

정확도를 밝히지 않은 그래프는 '그럴듯한 그림'일 뿐이다. 몇 %가 맞는지,
어디서 틀리는지 말할 수 있어야 쓸 수 있다.
"""

import argparse
import io
import json
import random
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "web" / "graph-data.json"

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 아는 사실 ────────────────────────────────────────────────────────────────
# 사람이 확인 없이도 자동으로 채점할 수 있는 것들. 하나라도 틀리면 어딘가
# 잘못된 것이다. ETL 의 '정답지'가 한 일을 지식그래프에서도 한다.
FACTS = [
    # (설명, 검사)
    ("신남방정책은 문재인 정부 것이다",      lambda g: g.admin("신남방정책") == "문재인"),
    ("신북방정책은 문재인 정부 것이다",      lambda g: g.admin("신북방정책") == "문재인"),
    ("인태전략은 윤석열 정부 것이다",        lambda g: g.admin("인태전략") == "윤석열"),
    ("담대한구상은 윤석열 정부 것이다",      lambda g: g.admin("담대한구상") == "윤석열"),
    ("동북아평화협력구상은 박근혜 정부 것이다", lambda g: g.admin("동북아평화협력구상") == "박근혜"),
    ("포용정책은 김대중 정부 것이다",        lambda g: g.admin("포용정책") == "김대중"),
    ("유라시아이니셔티브는 박근혜 정부 것이다", lambda g: g.admin("유라시아이니셔티브") == "박근혜"),
    ("외환위기는 1997~1998년이 최고다",      lambda g: g.peak("외환위기") in (1997, 1998)),
    ("우크라이나전쟁은 2022년 이후다",       lambda g: g.first("우크라이나전쟁") >= 2021),
    ("천안문사태는 1989~1990년이 최고다",    lambda g: g.peak("천안문사태") in (1989, 1990)),
    ("테러사태는 2001년이 최고다",           lambda g: g.peak("테러사태") == 2001),
    ("북한은 유엔과 이어져 있다",            lambda g: g.linked("북한", "유엔")),
    ("북한은 IAEA와 이어져 있다",            lambda g: g.linked("북한", "IAEA")),
    ("북한은 미국과 이어져 있다",            lambda g: g.linked("북한", "미국")),
    ("신남방정책은 아세안과 이어져 있다",     lambda g: g.linked("신남방정책", "아세안")),
    ("교토의정서는 기후변화협약과 이어져 있다", lambda g: g.linked("교토의정서", "기후변화협약")),
    ("미국이 가장 많이 언급된 나라다",        lambda g: g.top("country") == "미국"),
    ("2004년은 원본 결손이 기록돼 있다",     lambda g: "2004" in g.d["meta"].get("gaps", {})),
]


class G:
    def __init__(self, d):
        self.d = d
        self.n = {x["id"]: x for x in d["nodes"]}
        self.l = {(x["source"], x["target"]) for x in d["links"]}

    def admin(self, i):
        x = self.n.get(i)
        return max(x["byAdmin"], key=x["byAdmin"].get) if x else None

    def peak(self, i):
        x = self.n.get(i)
        return int(x["peak"]) if x else None

    def first(self, i):
        x = self.n.get(i)
        return int(x["first"]) if x else None

    def linked(self, a, b):
        return (a, b) in self.l or (b, a) in self.l

    def top(self, kind):
        c = [x for x in self.d["nodes"] if x["kind"] == kind]
        return c[0]["id"] if c else None


def mark(text, a, b):
    for w in (a, b):
        text = re.sub(re.escape(w), f"【{w}】", text, count=1)
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--facts", action="store_true", help="아는 사실로 자동 채점")
    ap.add_argument("--n", type=int, default=40, help="표본 개수")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    d = json.loads(DATA.read_text(encoding="utf-8"))
    g = G(d)

    if a.facts:
        print("=" * 74)
        print("아는 사실로 채점")
        print("=" * 74)
        ok = 0
        for desc, test in FACTS:
            try:
                r = bool(test(g))
            except Exception:
                r = False
            ok += r
            print(f"  {'통과' if r else '실패'}  {desc}")
        print(f"\n  {ok}/{len(FACTS)}건 통과 ({ok/len(FACTS)*100:.0f}%)")
        return

    labeled = [l for l in d["links"] if l["rel"] and l.get("sample")]
    random.seed(a.seed)
    sample = random.sample(labeled, min(a.n, len(labeled)))
    print("=" * 74)
    print(f"관계 라벨 표본 {len(sample)}개 — 근거 문장과 나란히 본다")
    print(f"(전체 관계 {len(d['links']):,}개 중 라벨 붙은 것 "
          f"{sum(1 for l in d['links'] if l['rel']):,}개)")
    print("=" * 74)
    for i, l in enumerate(sample, 1):
        s = l["sample"]
        print(f"\n{i:>3}. [{l['rel']}] {l['source']} — {l['target']}  "
              f"(확신 {l['relConf']} · 함께 {l['weight']}회)")
        print(f"     {s['year']}년: {mark(s['text'], l['source'], l['target'])[:190]}")


if __name__ == "__main__":
    main()
