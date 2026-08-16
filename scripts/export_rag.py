"""지식그래프를 RAGAs 로 검사할 수 있는 꼴로 내보낸다.

RAGAs 는 네 칸을 요구한다.

    question      물음
    contexts      그 물음에 답하려고 **찾아온 문장들**
    answer        그 문장들로 만든 답 (RAG 파이프라인이 채운다)
    ground_truth  정답 (사람이 확인한 것)

여기서 '찾아오기(retrieval)'는 지식그래프가 한다. 물음에 나온 이름을 그래프에서
찾고, 그 점에 달린 원문 문장을 가져온다. 그러니 RAGAs 가 재는 것은 곧
**이 그래프가 근거를 제대로 물어오는가**다.

    python scripts/export_rag.py                    물음 만들고 문장 붙이기
    python scripts/export_rag.py --out eval/rag.jsonl

산출물 한 줄:
    {"question": "...", "contexts": ["...", ...], "ground_truth": "...",
     "meta": {"entity": "북한", "kind": "country", "type": "정의", ...}}

answer 칸은 비워 둔다. 답을 만드는 것은 이 프로그램의 일이 아니다 —
LLM 을 붙여 채운 뒤 RAGAs 에 넣으면 된다.
"""

import argparse
import io
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GRAPH = PROJECT_ROOT / "web" / "graph-data.json"
OUT = PROJECT_ROOT / "eval" / "rag.jsonl"

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KIND_KO = {"country": "나라", "org": "국제기구", "policy": "정책",
           "event": "사건", "treaty": "조약"}

# 물음의 틀. 지식그래프가 답할 수 있는 것만 묻는다 — 그래프에 없는 것을 물으면
# 검사하는 것이 그래프가 아니라 LLM 의 사전지식이 된다.
TEMPLATES = [
    # (종류, 물음 틀, 정답을 어떻게 만드나)
    ("정의", "외교백서에서 {e}은(는) 어떤 맥락으로 다루어졌나?", None),
    ("시기", "{e}이(가) 외교백서에 가장 많이 등장한 해는 언제인가?",
     lambda n, g: f"{n['peak']}년이다. 백서 분량을 감안하면 {n['peakRate']}년이 가장 높다."),
    ("정권", "{e}을(를) 가장 많이 다룬 정부는 어디인가?",
     lambda n, g: f"{max(n['byAdmin'], key=n['byAdmin'].get)} 정부다 "
                  f"({max(n['byAdmin'].values())}회)."),
    ("관계", "외교백서에서 {e}과(와) 함께 가장 자주 언급된 것은 무엇인가?",
     lambda n, g: (lambda t: f"{t[0]}이다 (같은 문장에 {t[1]}회 함께 나온다)."
                   if t else None)(g.top_partner(n["id"]))),
]


class Graph:
    def __init__(self, d):
        self.d = d
        self.nodes = {n["id"]: n for n in d["nodes"]}
        self.links = d["links"]

    def top_partner(self, i):
        best = None
        for l in self.links:
            if l["source"] == i or l["target"] == i:
                if best is None or l["weight"] > best[1]:
                    best = (l["target"] if l["source"] == i else l["source"], l["weight"])
        return best

    def rel_links(self, i):
        return [l for l in self.links
                if l["rel"] and (l["source"] == i or l["target"] == i)]


def contexts_for(node: dict, g: Graph, k: int) -> list[dict]:
    """그 점의 근거 문장. **출처를 함께 담는다** — RAGAs 는 문장만 보지만,
    사람이 결과를 확인하려면 어느 백서 몇 쪽인지 알아야 한다."""
    return node.get("docs", [])[:k]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--k", type=int, default=6, help="물음 하나에 붙일 문장 수")
    ap.add_argument("--min-docs", type=int, default=3,
                    help="근거가 이보다 적은 개체는 묻지 않는다")
    a = ap.parse_args()

    if not GRAPH.exists():
        raise SystemExit(f"[ERROR] {GRAPH} 가 없다. mine_entities.py 를 먼저 돌린다.")
    d = json.loads(GRAPH.read_text(encoding="utf-8"))
    g = Graph(d)

    rows = []
    skipped = 0
    for n in d["nodes"]:
        docs = contexts_for(n, g, a.k)
        if len(docs) < a.min_docs:
            skipped += 1
            continue
        for qtype, tmpl, truth_fn in TEMPLATES:
            truth = None
            if truth_fn:
                try:
                    truth = truth_fn(n, g)
                except Exception:
                    truth = None
                if truth is None:      # 정답을 만들 수 없으면 묻지 않는다
                    continue
            rows.append({
                "question": tmpl.format(e=n["id"]),
                "contexts": [x["text"] for x in docs],
                "answer": "",                       # RAG 파이프라인이 채운다
                "ground_truth": truth or "",
                "meta": {
                    "entity": n["id"], "kind": n["kind"], "kindKo": KIND_KO[n["kind"]],
                    "qtype": qtype,
                    "total": n["total"], "docCount": n.get("docCount"),
                    "sources": [{"year": x["year"], "admin": x["admin"],
                                 "chapter": x.get("chapter"), "page": x.get("page"),
                                 "src": x.get("src"), "id": x.get("id")} for x in docs],
                },
            })

    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                     encoding="utf-8")

    from collections import Counter
    c = Counter(r["meta"]["qtype"] for r in rows)
    k = Counter(r["meta"]["kindKo"] for r in rows)
    print(f"물음 {len(rows):,}개 · 개체 {len(d['nodes']) - skipped}개 "
          f"(근거 부족으로 건너뛴 것 {skipped}개)")
    print("  종류별: " + " · ".join(f"{x} {y}" for x, y in c.most_common()))
    print("  대상별: " + " · ".join(f"{x} {y}" for x, y in k.most_common()))
    print(f"  정답 있는 물음 {sum(1 for r in rows if r['ground_truth']):,}개")
    print(f"→ {a.out}  ({a.out.stat().st_size/1024:.0f} KB)")
    print()
    print("RAGAs 에 넣는 법:")
    print("    import json, datasets, ragas")
    print("    rows = [json.loads(l) for l in open('eval/rag.jsonl', encoding='utf-8')]")
    print("    # answer 칸을 LLM 으로 채운 뒤")
    print("    ds = datasets.Dataset.from_list(rows)")
    print("    ragas.evaluate(ds, metrics=[context_precision, context_recall,")
    print("                                faithfulness, answer_relevancy])")


if __name__ == "__main__":
    main()
