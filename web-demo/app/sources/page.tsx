"use client";

/* eslint-disable jsx-a11y/no-noninteractive-tabindex -- the wide semantic table needs a keyboard-focusable scroll region */

import { useEffect, useMemo, useState } from "react";
import { SiteFooter, SiteHeader } from "../../components/SiteHeader";
import styles from "./sources.module.css";

type Edition = {
  coverageYear: number;
  title: string;
  publishedYear: number;
  administration: string;
  brand: string | null;
  section: {
    chapter: number | null;
    section: number | null;
    label: string | null;
    page: number | null;
  };
  markStyle: string | null;
  status: string;
  sourceFiles: string[];
  note: string | null;
};

type Priority = {
  id: string;
  coverageYear: number;
  ordinal: number;
  title: string;
};

type ArchiveData = {
  meta: {
    builtAt: string;
    coverage: {
      from: number;
      to: number;
      withPriorities: number;
      total: number;
    };
  };
  editions: Edition[];
  priorities: Priority[];
};

const STATUS_ORDER = ["verified", "partial", "blocked", "no-section", "pending", "from-preface"];

const statusLabels: Record<string, string> = {
  verified: "원문 대조 완료",
  partial: "일부 확인",
  blocked: "원본 결손",
  "no-section": "해당 절 없음",
  pending: "대조 대기",
  "from-preface": "발간사 대체",
};

function statusLabel(status: string) {
  return statusLabels[status] ?? status;
}

function statusClass(status: string) {
  if (status === "verified") return styles.verified;
  if (status === "partial") return styles.partial;
  if (status === "blocked") return styles.blocked;
  if (status === "no-section") return styles.noSection;
  return styles.pending;
}

function sectionLabel(edition: Edition) {
  const numberedLocation = [
    edition.section.chapter ? `제${edition.section.chapter}장` : null,
    edition.section.section ? `제${edition.section.section}절` : null,
    edition.section.page ? `${edition.section.page}쪽` : null,
  ].filter(Boolean);

  if (edition.section.label && numberedLocation.length) {
    return `${numberedLocation.join(" · ")} · ${edition.section.label}`;
  }
  if (edition.section.label) return edition.section.label;
  if (numberedLocation.length) return numberedLocation.join(" · ");
  return "위치 정보 없음";
}

export default function SourcesPage() {
  const [archive, setArchive] = useState<ArchiveData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedStatus, setSelectedStatus] = useState("all");

  useEffect(() => {
    const controller = new AbortController();

    fetch("/data.json", { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("자료를 불러오지 못했습니다.");
        return response.json() as Promise<ArchiveData>;
      })
      .then(setArchive)
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "자료를 불러오지 못했습니다.");
      });

    return () => controller.abort();
  }, []);

  const sortedEditions = useMemo(
    () => [...(archive?.editions ?? [])].sort((a, b) => a.coverageYear - b.coverageYear),
    [archive],
  );

  const countsByStatus = useMemo(() => {
    const counts = new Map<string, number>();
    sortedEditions.forEach((edition) => counts.set(edition.status, (counts.get(edition.status) ?? 0) + 1));
    return counts;
  }, [sortedEditions]);

  const availableStatuses = useMemo(() => {
    const observed = [...countsByStatus.keys()];
    return [
      ...STATUS_ORDER.filter((status) => observed.includes(status)),
      ...observed.filter((status) => !STATUS_ORDER.includes(status)).sort(),
    ];
  }, [countsByStatus]);

  const filteredEditions = useMemo(
    () =>
      selectedStatus === "all"
        ? sortedEditions
        : sortedEditions.filter((edition) => edition.status === selectedStatus),
    [selectedStatus, sortedEditions],
  );

  const priorityCounts = useMemo(() => {
    const counts = new Map<number, number>();
    (archive?.priorities ?? []).forEach((priority) => {
      counts.set(priority.coverageYear, (counts.get(priority.coverageYear) ?? 0) + 1);
    });
    return counts;
  }, [archive]);

  const totalPriorities = archive?.priorities.length ?? 0;
  const editionsWithItems = sortedEditions.filter((edition) => (priorityCounts.get(edition.coverageYear) ?? 0) > 0).length;

  return (
    <div className={styles.page}>
      <SiteHeader />
      <main className={styles.main}>
        <section className={styles.hero} aria-labelledby="sources-title">
          <div>
            <p className={styles.kicker}>자료 현황 · SOURCE REGISTER</p>
            <h1 id="sources-title">비어 있는 해까지<br />자료로 남깁니다</h1>
          </div>
          <div className={styles.heroNote}>
            <p>
              1989~2025 대상연도의 발간분, 원문 위치, 추출 상태와 검수 메모를 공개합니다.
              항목이 없는 것은 정책의 부재가 아니라 자료 상태일 수 있습니다.
            </p>
            <a href="/data.json" download>원본 데이터 JSON 내려받기 ↓</a>
          </div>
        </section>

        {error ? (
          <div className={styles.error} role="alert">
            <h2>자료 현황을 표시할 수 없습니다.</h2>
            <p>{error}</p>
          </div>
        ) : !archive ? (
          <div className={styles.loading} role="status">연도별 자료 상태를 불러오고 있습니다.</div>
        ) : (
          <>
            <section className={styles.summarySection} aria-labelledby="summary-title">
              <div className={styles.sectionLead}>
                <div>
                  <p className={styles.sectionNumber}>01 / 전체 현황</p>
                  <h2 id="summary-title">{archive.meta.coverage.from}–{archive.meta.coverage.to}</h2>
                </div>
                <p>자료 생성일 {archive.meta.builtAt}</p>
              </div>

              <dl className={styles.summaryGrid}>
                <div>
                  <dt>대상연도</dt>
                  <dd>{sortedEditions.length}<span>개년</span></dd>
                </div>
                <div>
                  <dt>원문 대조 완료</dt>
                  <dd>{countsByStatus.get("verified") ?? 0}<span>개년</span></dd>
                </div>
                <div>
                  <dt>항목 입력 연도</dt>
                  <dd>{editionsWithItems}<span>개년</span></dd>
                </div>
                <div>
                  <dt>확인된 항목</dt>
                  <dd>{totalPriorities}<span>개</span></dd>
                </div>
              </dl>
            </section>

            <section className={styles.registerSection} aria-labelledby="register-title">
              <div className={styles.sectionLead}>
                <div>
                  <p className={styles.sectionNumber}>02 / 연도별 색인</p>
                  <h2 id="register-title">발간분과 검수 상태</h2>
                </div>
                <p className={styles.resultCount} aria-live="polite">
                  전체 {sortedEditions.length}개년 중 {filteredEditions.length}개년 표시
                </p>
              </div>

              <fieldset className={styles.filters}>
                <legend>자료 상태로 필터</legend>
                <button
                  type="button"
                  className={selectedStatus === "all" ? styles.active : undefined}
                  aria-pressed={selectedStatus === "all"}
                  onClick={() => setSelectedStatus("all")}
                >
                  <span>전체</span>
                  <strong>{sortedEditions.length}</strong>
                </button>
                {availableStatuses.map((status) => (
                  <button
                    key={status}
                    type="button"
                    className={selectedStatus === status ? styles.active : undefined}
                    aria-pressed={selectedStatus === status}
                    onClick={() => setSelectedStatus(status)}
                  >
                    <span>{statusLabel(status)}</span>
                    <strong>{countsByStatus.get(status) ?? 0}</strong>
                  </button>
                ))}
              </fieldset>

              <div
                className={styles.tableScroll}
                role="region"
                aria-label="연도별 외교백서 자료 현황 표"
                tabIndex={0}
              >
                <table>
                  <caption>
                    1989년부터 2025년까지 외교백서의 대상연도, 발간분, 정부, 자료 상태,
                    확인 항목 수, 원문 위치와 출처 파일 및 검수 메모
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">대상연도</th>
                      <th scope="col">발간분</th>
                      <th scope="col">정부</th>
                      <th scope="col">자료 상태</th>
                      <th scope="col">항목 수</th>
                      <th scope="col">원문 위치</th>
                      <th scope="col">출처 파일 · 메모</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredEditions.map((edition) => {
                      const count = priorityCounts.get(edition.coverageYear) ?? 0;
                      return (
                        <tr key={edition.coverageYear}>
                          <th scope="row" className={styles.yearCell}>{edition.coverageYear}</th>
                          <td>
                            <strong>{edition.title}</strong>
                            <small>{edition.publishedYear}년 발간</small>
                          </td>
                          <td>
                            {edition.administration}
                            {edition.brand && <small>{edition.brand}</small>}
                          </td>
                          <td>
                            <span className={`${styles.status} ${statusClass(edition.status)}`}>
                              {statusLabel(edition.status)}
                            </span>
                          </td>
                          <td className={styles.countCell}>
                            <strong>{count}</strong>
                            <small>{count ? "개 확인" : "확인 없음"}</small>
                          </td>
                          <td className={styles.locationCell}>{sectionLabel(edition)}</td>
                          <td className={styles.sourceCell}>
                            {edition.sourceFiles.length ? (
                              <ul>
                                {edition.sourceFiles.map((file) => <li key={file}>{file}</li>)}
                              </ul>
                            ) : (
                              <span className={styles.noFile}>출처 파일 없음</span>
                            )}
                            {edition.note && <p>{edition.note.replaceAll("**", "")}</p>}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {!filteredEditions.length && (
                <p className={styles.empty} role="status">이 상태에 해당하는 연도가 없습니다.</p>
              )}
            </section>

            <aside className={styles.readingNote} aria-labelledby="status-guide-title">
              <p className={styles.sectionNumber}>03 / 상태 읽는 법</p>
              <h2 id="status-guide-title">0개는 ‘없음’과 같은 말이 아닙니다.</h2>
              <div>
                <p><strong>일부 확인</strong>은 목록 일부만 원문과 대조되었음을 뜻합니다.</p>
                <p><strong>원본 결손</strong>은 필요한 쪽이 없거나 읽을 수 없어 항목을 확정하지 못한 상태입니다.</p>
                <p><strong>해당 절 없음</strong>은 판본 편제에 「외교정책 기조」 절 자체가 없는 경우입니다.</p>
              </div>
            </aside>
          </>
        )}
      </main>
      <SiteFooter />
    </div>
  );
}
