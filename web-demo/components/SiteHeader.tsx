"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./site-header.module.css";

const navigation = [
  { href: "/", label: "홈", match: "/" },
  { href: "/timeline", label: "전체 시간축", match: "/timeline" },
  { href: "/governments/roh", label: "정부별 그래프", match: "/governments" },
  { href: "/transitions", label: "정권 이음매", match: "/transitions" },
  { href: "/years/2025", label: "2025 분석", match: "/years" },
  { href: "/sources", label: "자료 현황", match: "/sources" },
] as const;

function isCurrentPath(pathname: string, match: string) {
  if (match === "/") return pathname === "/";
  return pathname === match || pathname.startsWith(`${match}/`);
}

export function SiteHeader() {
  const pathname = usePathname();

  return (
    <header className={styles.header}>
      <div className={styles.inner}>
        <Link className={styles.brand} href="/" aria-label="외교의 순서 홈">
          <span className={styles.brandKicker}>대한민국 외교백서 아카이브</span>
          <span className={styles.brandTitle}>외교의 순서</span>
        </Link>

        <nav className={styles.navigation} aria-label="주요 탐색">
          <ul className={styles.navigationList}>
            {navigation.map((item) => {
              const current = isCurrentPath(pathname, item.match);
              return (
                <li key={item.href}>
                  <Link
                    className={styles.navigationLink}
                    href={item.href}
                    aria-current={current ? "page" : undefined}
                  >
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        <p className={styles.edition}>1989—2025<br />ARCHIVE 01</p>
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className={styles.footer}>
      <div className={styles.footerInner}>
        <p className={styles.footerTitle}>외교의 순서</p>
        <p className={styles.footerCopy}>
          외교백서의 배열 순서를 원문 근거와 함께 읽는 지식 아카이브
        </p>
        <Link className={styles.footerLink} href="/sources">자료와 검수 기준 보기 →</Link>
      </div>
    </footer>
  );
}

export default SiteHeader;
