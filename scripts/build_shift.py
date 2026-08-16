"""기능 2 화면을 만든다 — 정권별 외교정책의 시간 변화.

    python scripts/build_shift.py

`web/shift.html` 의 /*DATA*/ 자리에 두 자료를 함께 끼워 넣는다.

    theme-data.json   장면 1 — 주제 흐름   (scripts/themes.py --json)
    shift-data.json   장면 2·3 — 변화량과 들고 난 말 (scripts/policy_shift.py --json)
"""

import io
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
THEME = PROJECT_ROOT / "web" / "theme-data.json"
SHIFT = PROJECT_ROOT / "web" / "shift-data.json"
TEMPLATE = PROJECT_ROOT / "web" / "shift.html"
OUT = PROJECT_ROOT / "web" / "shift-demo.html"


def need(p: Path, how: str) -> dict:
    if not p.exists():
        raise SystemExit(f"[ERROR] {p} 가 없다. {how} 를 먼저 돌린다.")
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    theme = need(THEME, "python scripts/themes.py --json")
    shift = need(SHIFT, "python scripts/policy_shift.py --json")

    # 장면 1 에 필요한 것만 싣는다. 절 제목 920개까지 넣으면 화면이 무거워지고,
    # 그 목록은 색인 화면(toc-demo.html)이 이미 보여준다.
    slim = {"meta": theme["meta"], "byYear": theme["byYear"]}
    payload = json.dumps({"theme": slim, "shift": shift},
                         ensure_ascii=False, separators=(",", ":"))

    html = TEMPLATE.read_text(encoding="utf-8")
    new, n = re.subn(r"/\*DATA\*/.*?/\*DATA\*/", lambda _: payload, html, count=1, flags=re.S)
    if not n:
        raise SystemExit("[ERROR] 틀에서 /*DATA*/ 자리를 찾지 못했다.")
    OUT.write_text(new, encoding="utf-8")

    print(f"줄기 {len(theme['meta']['themes'])}개 · 연도 {len(theme['meta']['years'])}개 · "
          f"이웃한 해 {len(shift['steps'])}쌍")
    print(f"→ {OUT}  ({OUT.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
