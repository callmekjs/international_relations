"""연도별로 (1) 기조 절 리드와 (2) 「주요 외교시책」 절의 인쇄된 번호 목록을 함께 보여준다.

번호 붙은 목록이 기조 절 안에 있는 해도 있고 다음 절에 있는 해도 있다.
2002년처럼 기조 절이 통째로 산문인 해는 번호가 아예 다음 절에만 있다.
그래서 두 곳을 같이 봐야 그 해의 '인쇄된 순서'를 놓치지 않는다.

실행:
    python scripts/show_items.py 2000 2002 2003
"""

import io
import re
import sys

from stage_io import PROJECT_ROOT, REPORTS_ROOT

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

TEXT_ROOT = PROJECT_ROOT / "text"
SECTIONS = REPORTS_ROOT / "sections"

# 기조 절 다음에 오는 '항목을 번호로 받는 절'. 이름이 판마다 다르다 —
# 「주요 외교시책」(1998~2003) / 「주요 외교 성과」(2004~) 등.
_MEASURES = re.compile(
    r"(?:제\s*\d{1,2}\s*[절장]\s*)?(?:\d{4}\s*년\s*도?\s*)?"
    r"(?:" + r"\s*".join("주요외교시책") + r"|" + r"\s*".join("주요외교성과")
    + r"|" + r"\s*".join("주요외교활동") + r")")

# 원문자·로마숫자로 번호를 매기는 판도 있다(2006 정책목표Ⅰ~Ⅴ, 2007 ①~⑤).
_CIRCLED = re.compile(r"[①-⑮]\s*(.{0,60})")
_ROMAN = re.compile(r"정책목표\s*([ⅠⅡⅢⅣⅤⅥⅦⅧ])\s*[:：]?\s*(.{0,60})")

# 번호가 붙은 줄. 뒤에 쪽번호가 붙는 목차 줄도 함께 잡는다.
_NUMBERED = re.compile(r"^\s*(\d{1,2})\s*[.．]\s*(\S.{3,70}?)\s*(\d{1,3})?\s*$")

# 서수 낱말
_ORDINAL_WORD = re.compile(
    r"(첫째|둘째|셋째|넷째|다섯째|여섯째|일곱째|여덟째|아홉째|열째)\s*[,，]?\s*(.{0,90})")


def squeeze(s: str) -> str:
    s = re.sub(r"\n[ \t]*\n+", "\n", s)
    return re.sub(r"[ \t]{2,}", " ", s).strip()


def main() -> None:
    args = sys.argv[1:]
    lead = 1300
    if "--lead" in args:
        i = args.index("--lead")
        lead = int(args[i + 1])
        del args[i:i + 2]

    for year in [int(a) for a in args if a.isdigit()]:
        print(f"\n{'=' * 78}\n{year}\n{'=' * 78}")

        p = SECTIONS / f"{year}.md"
        if p.exists():
            m = re.search(r"```\n(.*?)\n```", p.read_text(encoding="utf-8"), re.S)
            if m:
                print("--- 기조 절 리드 ---")
                print(squeeze(m.group(1))[:lead])

        text = (TEXT_ROOT / f"{year}.txt").read_text(encoding="utf-8")

        ords_ = _ORDINAL_WORD.findall(text)
        if ords_:
            print("\n--- 서수 낱말로 나열된 자리 ---")
            seen = set()
            for word, rest in ords_:
                if word in seen:
                    continue
                seen.add(word)
                print(f"  {word}, {squeeze(rest)[:80]}")

        circled = _CIRCLED.findall(text)
        if circled:
            print("\n--- 원문자(①②③)로 나열된 자리 ---")
            for rest in circled[:12]:
                print(f"  {squeeze(rest)[:70]}")

        romans = _ROMAN.findall(text)
        if romans:
            print("\n--- 정책목표 Ⅰ~Ⅴ ---")
            seen_r = set()
            for num, rest in romans:
                if num in seen_r:
                    continue
                seen_r.add(num)
                print(f"  {num}: {squeeze(rest)[:70]}")

        hits = list(_MEASURES.finditer(text))
        if hits:
            print(f"\n--- 「주요 외교시책」 절의 번호 목록 ({len(hits)}곳에서 발견) ---")
            for h in hits[:2]:
                seg = text[h.start(): h.start() + 2500]
                nums = [(int(m.group(1)), squeeze(m.group(2)))
                        for m in (_NUMBERED.match(ln) for ln in seg.splitlines()) if m]
                if not nums:
                    continue
                print(f"  [글자 {h.start():,}]")
                last = 0
                for n, title in nums:
                    if n <= last or n > last + 1:   # 1,2,3… 으로 이어지는 줄만
                        if n != 1:
                            continue
                    last = n
                    print(f"    {n}. {title}")
                print()


if __name__ == "__main__":
    main()
