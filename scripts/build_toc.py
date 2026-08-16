"""색인 화면을 만든다. web/toc.html 의 /*DATA*/ 자리에 색인을 끼워 넣는다.

    python scripts/build_toc.py

`graph.html` → `graph-demo.html` 과 같은 방식이다. 틀과 자료를 따로 두어,
자료가 바뀌어도 틀을 손대지 않는다.
"""

import io
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX = PROJECT_ROOT / "corpus" / "index.jsonl"
TEMPLATE = PROJECT_ROOT / "web" / "toc.html"
OUT = PROJECT_ROOT / "web" / "toc-demo.html"

# 채점 결과(scripts/audit_index.py 실측). 화면 아래 각주에 그대로 적는다.
# 숫자를 화면에 박아 넣지 않고 여기 한 곳에서만 관리한다.
AUDIT = {"years": 22, "gold": 552, "hit": 496, "rate": 89.9}


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if not INDEX.exists():
        raise SystemExit(f"[ERROR] {INDEX} 가 없다. scripts/index.py --write 를 먼저 돌린다.")

    rows = [json.loads(l) for l in INDEX.open(encoding="utf-8")]
    data = {"rows": rows, "audit": AUDIT}
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    html = TEMPLATE.read_text(encoding="utf-8")
    new, n = re.subn(r"/\*DATA\*/.*?/\*DATA\*/", lambda _: payload, html, count=1, flags=re.S)
    if not n:
        raise SystemExit("[ERROR] 틀에서 /*DATA*/ 자리를 찾지 못했다.")
    OUT.write_text(new, encoding="utf-8")

    years = sorted({r["연도"] for r in rows})
    secs = [r for r in rows if r["절"] is not None]
    print(f"색인 {len(rows)}줄 · {len(years)}개년 · 절 {len(secs)}개")
    print(f"→ {OUT}  ({OUT.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
