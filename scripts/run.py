"""
파이프라인 실행기 — 순서를 강제한다.

각 단계가 저마다 잘 돌아도 사람이 순서를 틀리면 결과가 어긋난다.
extract 를 다시 돌리고 verify 를 건너뛰면, 원문이 바뀌었는데 옛 인용문이
그대로 남은 채 data.json 이 나간다. 그런 일이 없도록 관문을 순서대로 지난다.

    extract  →  audit  →  verify  →  build
                 ↑ 여기서 막히면 아래로 못 간다

실행
    python scripts/run.py                # 전체 (추출은 이미 있으면 건너뜀)
    python scripts/run.py --from audit   # 표만 고쳤을 때
    python scripts/run.py --strict       # WARN 도 실패로 친다
"""

import io
import subprocess
import sys
import time
from pathlib import Path

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

# (단계명, 스크립트, 설명, 실패 시 멈추는가)
STAGES = [
    ("extract", "extract.py", "원본 → 텍스트", False),   # 스캔본 실패는 알려진 것이라 안 세움
    ("audit",   "audit.py",   "전 단계 점검",   True),
    ("verify",  "verify.py",  "인용 원문 대조", True),
    ("build",   "build.py",   "data.json 생성", True),
]
NAMES = [s[0] for s in STAGES]


def main() -> None:
    args = sys.argv[1:]
    strict = "--strict" in args
    start = "extract"
    if "--from" in args:
        start = args[args.index("--from") + 1]
        if start not in NAMES:
            print(f"[ERROR] 알 수 없는 단계: {start}  (가능: {', '.join(NAMES)})")
            sys.exit(2)

    todo = STAGES[NAMES.index(start):]
    t0 = time.time()

    for name, script, label, gate in todo:
        cmd = [sys.executable, str(SCRIPTS / script)]
        if name == "audit" and strict:
            cmd.append("--strict")
        print(f"\n{'=' * 60}\n[{name}] {label}\n{'=' * 60}")
        rc = subprocess.run(cmd, cwd=ROOT).returncode
        if rc != 0 and gate:
            print(f"\n[중단] {name} 에서 막혔다 (exit {rc}). 여기를 고치기 전에는 다음으로 안 간다.")
            sys.exit(rc)
        if rc != 0:
            print(f"\n[계속] {name} 이 {rc} 로 끝났지만 알려진 실패라 진행한다.")

    print(f"\n{'=' * 60}")
    print(f"  전 단계 통과 — 소요 {(time.time() - t0) / 60:.1f}분")
    print(f"  결과: {ROOT / 'data.json'}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
