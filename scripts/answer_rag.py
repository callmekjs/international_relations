"""RAGAs 평가용 답을 Claude 로 채운다.

export_rag.py 가 만든 eval/rag.jsonl 의 `answer` 칸이 비어 있다. 이 프로그램이
각 물음을 **가져온 문장(contexts)만 근거로** 답하게 해서 그 칸을 채운다.

    python scripts/answer_rag.py --limit 5      다섯 개만 시험
    python scripts/answer_rag.py                전부 (묶음 처리, 값이 절반)
    python scripts/answer_rag.py --sync         하나씩 즉시 (묶음이 막힐 때)

왜 '가져온 문장만'인가 — RAGAs 의 faithfulness 는 "답이 근거에 실제로 뿌리를
두고 있나"를 잰다. 모델이 아는 지식으로 답해 버리면 지식그래프가 근거를 잘
물어왔는지가 아니라 모델이 외교사를 아는지를 재게 된다.

    python scripts/answer_rag.py --score        RAGAs 로 채점 (답이 채워진 뒤)
"""

import argparse
import io
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
IN = PROJECT_ROOT / "eval" / "rag.jsonl"
OUT = PROJECT_ROOT / "eval" / "rag-answered.jsonl"

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

MODEL = "claude-opus-5"
MAX_TOKENS = 1024

SYSTEM = """당신은 한국 외교백서(1989~2025) 자료를 다루는 조사원입니다.

**주어진 발췌문만 근거로 답하십시오.** 발췌문에 없는 사실은 알고 있더라도 쓰지 마십시오.
발췌문으로 답할 수 없으면 "주어진 자료로는 알 수 없습니다"라고 쓰십시오.

두세 문장으로 답하십시오. 서론이나 맺음말 없이 답만 쓰십시오."""

USER = """다음은 외교백서에서 뽑은 발췌문입니다.

{contexts}

물음: {question}"""


def build(row: dict) -> dict:
    ctx = "\n\n".join(f"[발췌 {i}] {t}" for i, t in enumerate(row["contexts"], 1))
    return {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        # 발췌문을 읽고 요약하는 일이라 깊은 추론이 필요 없다. 낮은 노력으로
        # 값과 시간을 아낀다 — 대신 지어내지 않도록 지시를 엄하게 두었다.
        "output_config": {"effort": "low"},
        "system": SYSTEM,
        "messages": [{"role": "user", "content": USER.format(
            contexts=ctx, question=row["question"])}],
    }


def text_of(message) -> str:
    return next((b.text for b in message.content if b.type == "text"), "").strip()


def run_sync(client, rows) -> list[dict]:
    out = []
    for i, r in enumerate(rows, 1):
        msg = client.messages.create(**build(r))
        out.append({**r, "answer": text_of(msg)})
        print(f"\r   {i}/{len(rows)}", end="", flush=True)
    print()
    return out


def run_batch(client, rows) -> list[dict]:
    """묶음 처리 — 값이 절반이고, 552개쯤은 대개 한 시간 안에 끝난다."""
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    batch = client.messages.batches.create(requests=[
        Request(custom_id=f"q{i:05d}", params=MessageCreateParamsNonStreaming(**build(r)))
        for i, r in enumerate(rows)
    ])
    print(f"   묶음 {batch.id} 보냄 — 기다립니다")
    while True:
        b = client.messages.batches.retrieve(batch.id)
        if b.processing_status == "ended":
            break
        c = b.request_counts
        print(f"\r   처리중 {c.processing} · 끝남 {c.succeeded} · 실패 {c.errored}",
              end="", flush=True)
        time.sleep(20)
    print()

    # **결과는 보낸 순서대로 오지 않는다.** custom_id 로 짝을 맞춘다.
    answers = {}
    failed = 0
    for res in client.messages.batches.results(batch.id):
        if res.result.type == "succeeded":
            answers[res.custom_id] = text_of(res.result.message)
        else:
            failed += 1
            answers[res.custom_id] = ""
    if failed:
        print(f"   ! 실패 {failed}건 — 그 물음은 답이 빈 채로 남습니다")
    return [{**r, "answer": answers.get(f"q{i:05d}", "")} for i, r in enumerate(rows)]


def score(path: Path) -> None:
    """RAGAs 로 채점한다. 답이 채워진 뒤에 부른다."""
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    rows = [r for r in rows if r.get("answer")]
    if not rows:
        raise SystemExit("[ERROR] 답이 채워진 줄이 없다. 먼저 답을 만든다.")
    print(f"채점 대상 {len(rows):,}개")
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import (answer_relevancy, context_precision,
                                   context_recall, faithfulness)
    except ImportError as exc:
        raise SystemExit(f"[ERROR] ragas/datasets 가 필요하다: {exc}")

    ds = Dataset.from_list([
        {"question": r["question"], "contexts": r["contexts"],
         "answer": r["answer"], "ground_truth": r["ground_truth"]}
        for r in rows
    ])
    # context_recall 과 answer_relevancy 는 ground_truth 가 있어야 뜻이 있다.
    metrics = [faithfulness, answer_relevancy, context_precision]
    if any(r["ground_truth"] for r in rows):
        metrics.append(context_recall)
    print(evaluate(ds, metrics=metrics))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="앞에서 이만큼만")
    ap.add_argument("--sync", action="store_true", help="묶음 대신 하나씩")
    ap.add_argument("--score", action="store_true", help="채점만 한다")
    ap.add_argument("--in", dest="src", type=Path, default=IN)
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()

    if a.score:
        score(a.out if a.out.exists() else a.src)
        return

    if not a.src.exists():
        raise SystemExit(f"[ERROR] {a.src} 가 없다. export_rag.py 를 먼저 돌린다.")
    rows = [json.loads(l) for l in a.src.read_text(encoding="utf-8").splitlines()]
    if a.limit:
        rows = rows[:a.limit]

    import anthropic
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise SystemExit(
            "[ERROR] API 키가 없다.\n"
            "  PowerShell:  $env:ANTHROPIC_API_KEY = 'sk-ant-...'\n"
            "  키는 https://console.anthropic.com/settings/keys 에서 만든다")
    client = anthropic.Anthropic()

    print(f"물음 {len(rows):,}개 · {MODEL} · {'하나씩' if a.sync else '묶음(값 절반)'}")
    done = run_sync(client, rows) if a.sync else run_batch(client, rows)

    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in done) + "\n",
                     encoding="utf-8")
    filled = sum(1 for r in done if r["answer"])
    print(f"→ {a.out}  ({filled:,}/{len(done):,} 채워짐)")
    print("\n채점:  python scripts/answer_rag.py --score")


if __name__ == "__main__":
    main()
