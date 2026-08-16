"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { SiteFooter, SiteHeader } from "@/components/SiteHeader";
import styles from "./home.module.css";

type Edition = {
  coverageYear: number;
  administration: string;
  status: string;
};

type Priority = {
  coverageYear: number;
  ordinal: number;
  title: string;
};

type ArchiveData = {
  editions: Edition[];
  priorities: Priority[];
};

const entryPoints = [
  {
    index: "01",
    href: "/timeline",
    eyebrow: "흐름",
    title: "전체 시간축",
    description: "1989년부터 2025년까지, 해마다 먼저 놓인 외교 의제를 한 줄에서 따라갑니다.",
    action: "37년 펼쳐보기",
  },
  {
    index: "02",
    href: "/governments/roh",
    eyebrow: "깊이",
    title: "정부별 그래프",
    description: "정부에서 연도로, 다시 정책 우선순위와 원문 근거로 가지를 펼쳐 읽습니다.",
    action: "노무현 정부부터 보기",
  },
  {
    index: "03",
    href: "/transitions",
    eyebrow: "비교",
    title: "정권 이음매",
    description: "정권이 바뀌기 전과 후, 이어진 의제와 순서가 달라진 지점을 나란히 봅니다.",
    action: "교체 전후 비교하기",
  },
  {
    index: "04",
    href: "/sources",
    eyebrow: "근거",
    title: "자료 현황",
    description: "어떤 백서의 몇 쪽에서 가져왔는지, 원문 대조와 결측 상태까지 확인합니다.",
    action: "검수 기록 확인하기",
  },
] as const;

export default function Home() {
  const [archive, setArchive] = useState<ArchiveData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    fetch("/data.json", { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("자료를 불러오지 못했습니다.");
        return response.json() as Promise<ArchiveData>;
      })
      .then(setArchive)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "자료를 불러오지 못했습니다.");
      });

    return () => controller.abort();
  }, []);

  const summary = useMemo(() => {
    if (!archive) return null;

    const years = [...new Set(archive.editions.map((edition) => edition.coverageYear))]
      .sort((a, b) => a - b);
    const verifiedCount = archive.editions.filter((edition) => edition.status === "verified").length;
    const rohYears = archive.editions
      .filter((edition) => edition.administration === "노무현")
      .map((edition) => edition.coverageYear)
      .sort((a, b) => a - b);
    const firstRohYear = rohYears[0];
    const lastRohYear = rohYears.at(-1);
    const firstRohPriority = archive.priorities
      .filter((priority) => priority.coverageYear === firstRohYear)
      .sort((a, b) => a.ordinal - b.ordinal)[0];
    const lastRohPriority = archive.priorities
      .filter((priority) => priority.coverageYear === lastRohYear)
      .sort((a, b) => a.ordinal - b.ordinal)[0];

    return {
      firstYear: years[0],
      lastYear: years.at(-1),
      yearCount: years.length,
      priorityCount: archive.priorities.length,
      verifiedCount,
      editionCount: archive.editions.length,
      firstRohYear,
      lastRohYear,
      firstRohPriority,
      lastRohPriority,
    };
  }, [archive]);

  return (
    <div className={styles.page}>
      <SiteHeader />

      <main id="main-content" className={styles.main}>
        <section className={styles.hero} aria-labelledby="home-title">
          <div className={styles.heroGrid}>
            <div className={styles.heroLead}>
              <p className={styles.kicker}>대한민국 외교백서 · 우선순위 아카이브</p>
              <h1 id="home-title">
                외교는 무엇을<br />
                먼저 <em>말했는가</em>
              </h1>
              <p className={styles.introduction}>
                외교백서에 기록된 정책의 배열을 따라가면 한 시대가 무엇을 앞에 두었는지 보입니다.
                연도와 정부를 넘나들며 그 순서의 변화와 원문 근거를 함께 읽습니다.
              </p>
              <div className={styles.heroActions}>
                <Link className={styles.primaryAction} href="/timeline">전체 시간축 보기 <span aria-hidden="true">→</span></Link>
                <Link className={styles.secondaryAction} href="/governments/roh">대표 사례 읽기</Link>
              </div>
            </div>

            <aside className={styles.feature} aria-labelledby="feature-title">
              <div className={styles.featureHeading}>
                <p>대표 장면</p>
                <span>2003—2007</span>
              </div>
              <h2 id="feature-title">같은 정부 안에서도<br />첫 번째 의제는 움직입니다</h2>

              <div className={styles.priorityShift} aria-live="polite">
                <div>
                  <span>{summary?.firstRohYear ?? "2003"}</span>
                  <strong>01</strong>
                  <p>{summary?.firstRohPriority?.title ?? "자료 집계 중"}</p>
                </div>
                <span className={styles.shiftArrow} aria-hidden="true">↘</span>
                <div>
                  <span>{summary?.lastRohYear ?? "2007"}</span>
                  <strong>01</strong>
                  <p>{summary?.lastRohPriority?.title ?? "자료 집계 중"}</p>
                </div>
              </div>

              <Link className={styles.featureLink} href="/governments/roh">
                노무현 정부 5년의 가지 보기 <span aria-hidden="true">↗</span>
              </Link>
            </aside>
          </div>

          {error && <p className={styles.dataError} role="alert">{error} 잠시 후 다시 확인해 주세요.</p>}

          <dl className={styles.stats} aria-label="아카이브 자료 요약" aria-live="polite">
            <div>
              <dt>수록 연도</dt>
              <dd>{summary ? `${summary.firstYear}—${summary.lastYear}` : "—"}</dd>
              <dd className={styles.statNote}>{summary ? `${summary.yearCount}개 연도` : "집계 중"}</dd>
            </div>
            <div>
              <dt>정책 우선순위</dt>
              <dd>{summary ? summary.priorityCount.toLocaleString("ko-KR") : "—"}</dd>
              <dd className={styles.statNote}>백서 배열 항목</dd>
            </div>
            <div>
              <dt>원문 대조 완료</dt>
              <dd>{summary ? `${summary.verifiedCount}/${summary.editionCount}` : "—"}</dd>
              <dd className={styles.statNote}>연도별 백서 기준</dd>
            </div>
          </dl>
        </section>

        <section className={styles.directory} aria-labelledby="directory-title">
          <div className={styles.directoryHeading}>
            <div>
              <p>EXPLORE THE ARCHIVE</p>
              <h2 id="directory-title">네 갈래로 읽기</h2>
            </div>
            <p>메인은 길잡이만 남겼습니다. 궁금한 질문에서 탐색을 시작하세요.</p>
          </div>

          <nav className={styles.cardGrid} aria-label="아카이브 탐색 방식">
            {entryPoints.map((entry) => (
              <Link className={styles.card} href={entry.href} key={entry.href}>
                <div className={styles.cardMeta}>
                  <span>{entry.index}</span>
                  <small>{entry.eyebrow}</small>
                </div>
                <h3>{entry.title}</h3>
                <p>{entry.description}</p>
                <span className={styles.cardAction}>{entry.action} <b aria-hidden="true">→</b></span>
              </Link>
            ))}
          </nav>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
