"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { SiteFooter, SiteHeader } from "../../components/SiteHeader";
import styles from "./timeline.module.css";

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
  ordinalSource: string;
  title: string;
  quote: string;
  stream: string;
  source: {
    edition: string;
    chapter: number | null;
    section: number | null;
    page: number | null;
  };
  flags: string[];
};

type Stream = {
  id: string;
  label: string;
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
  streams: Stream[];
};

type AdministrationGroup = {
  administration: string;
  brand: string | null;
  editions: Edition[];
};

const ALL_ADMINISTRATIONS = "all";

const STATUS_LABELS: Record<string, string> = {
  verified: "원문 대조 완료",
  partial: "일부 확인",
  blocked: "원본 확인 불가",
  "no-section": "정책 기조 절 없음",
  "from-preface": "발간사 대체",
  pending: "검수 진행 중",
};

const STATUS_SYMBOLS: Record<string, string> = {
  verified: "●",
  partial: "◐",
  blocked: "×",
  "no-section": "—",
  "from-preface": "△",
  pending: "○",
};

const MARK_STYLE_LABELS: Record<string, string> = {
  bullet: "불릿 기호",
  circled: "원문자 번호(①·②…)",
  heading: "표·소제목 배열",
  "inline-lead": "문단 첫머리",
  number: "아라비아 숫자",
  "ordinal-word": "순서말(첫째·둘째…)",
  prose: "서술 순서",
  roman: "로마 숫자(Ⅰ·Ⅱ…)",
};

const FLAG_LABELS: Record<string, string> = {
  partial: "일부 확인",
  ocr: "OCR 판독",
  "heading-only": "제목만 확인",
  "lead-only": "리드 문장 확인",
  "from-preface": "발간사 대체",
  "title-lost": "제목 유실",
};

function statusLabel(status: string) {
  return STATUS_LABELS[status] ?? status;
}

function statusSymbol(status: string) {
  return STATUS_SYMBOLS[status] ?? "○";
}

function markStyleLabel(markStyle: string | null) {
  return markStyle ? (MARK_STYLE_LABELS[markStyle] ?? markStyle) : "형식 확인 중";
}

function flagLabel(flag: string) {
  return FLAG_LABELS[flag] ?? flag;
}

function formatSection(edition: Edition) {
  const location = [
    edition.section.chapter ? `제${edition.section.chapter}장` : null,
    edition.section.section ? `제${edition.section.section}절` : null,
    edition.section.page ? `${edition.section.page}쪽` : null,
  ].filter(Boolean);

  return location.length ? location.join(" · ") : "위치 정보 확인 중";
}

function formatPrioritySource(priority: Priority) {
  const location = [
    priority.source.edition,
    priority.source.chapter ? `제${priority.source.chapter}장` : null,
    priority.source.section ? `제${priority.source.section}절` : null,
    priority.source.page ? `${priority.source.page}쪽` : null,
  ].filter(Boolean);

  return location.join(" · ");
}

export default function TimelinePage() {
  const [archive, setArchive] = useState<ArchiveData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [reloadToken, setReloadToken] = useState(0);
  const [administrationFilter, setAdministrationFilter] = useState(ALL_ADMINISTRATIONS);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const yearButtonRefs = useRef<Array<HTMLButtonElement | null>>([]);

  useEffect(() => {
    const controller = new AbortController();

    fetch("/data.json", { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("자료를 불러오지 못했습니다.");
        return response.json() as Promise<ArchiveData>;
      })
      .then((data) => {
        if (!Array.isArray(data.editions) || !Array.isArray(data.priorities)) {
          throw new Error("자료 형식을 확인할 수 없습니다.");
        }

        const firstYear = [...data.editions]
          .sort((a, b) => a.coverageYear - b.coverageYear)[0]?.coverageYear;

        setArchive(data);
        setSelectedYear((current) =>
          current !== null && data.editions.some((edition) => edition.coverageYear === current)
            ? current
            : (firstYear ?? null),
        );
        setIsLoading(false);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "자료를 불러오지 못했습니다.");
        setIsLoading(false);
      });

    return () => controller.abort();
  }, [reloadToken]);

  const editions = useMemo(
    () => [...(archive?.editions ?? [])].sort((a, b) => a.coverageYear - b.coverageYear),
    [archive],
  );

  const prioritiesByYear = useMemo(() => {
    const index = new Map<number, Priority[]>();

    for (const priority of archive?.priorities ?? []) {
      const items = index.get(priority.coverageYear) ?? [];
      items.push(priority);
      index.set(priority.coverageYear, items);
    }

    for (const items of index.values()) {
      items.sort((a, b) => a.ordinal - b.ordinal);
    }

    return index;
  }, [archive]);

  const streamLabels = useMemo(
    () => new Map((archive?.streams ?? []).map((stream) => [stream.id, stream.label])),
    [archive],
  );

  const administrations = useMemo(
    () => Array.from(new Set(editions.map((edition) => edition.administration))),
    [editions],
  );

  const filteredEditions = useMemo(
    () =>
      administrationFilter === ALL_ADMINISTRATIONS
        ? editions
        : editions.filter((edition) => edition.administration === administrationFilter),
    [administrationFilter, editions],
  );

  const administrationGroups = useMemo(
    () =>
      filteredEditions.reduce<AdministrationGroup[]>((groups, edition) => {
        const current = groups.at(-1);
        if (current?.administration === edition.administration) {
          current.editions.push(edition);
        } else {
          groups.push({
            administration: edition.administration,
            brand: edition.brand,
            editions: [edition],
          });
        }
        return groups;
      }, []),
    [filteredEditions],
  );

  const visibleIndexByYear = useMemo(
    () => new Map(filteredEditions.map((edition, index) => [edition.coverageYear, index])),
    [filteredEditions],
  );

  const selectedEdition =
    editions.find((edition) => edition.coverageYear === selectedYear) ?? null;
  const selectedPriorities = selectedYear === null ? [] : prioritiesByYear.get(selectedYear) ?? [];
  const verifiedCount = editions.filter((edition) => edition.status === "verified").length;
  const totalPriorityCount = archive?.priorities.length ?? 0;

  function chooseAdministration(administration: string) {
    setAdministrationFilter(administration);

    if (administration !== ALL_ADMINISTRATIONS) {
      const first = editions.find((edition) => edition.administration === administration);
      if (first) setSelectedYear(first.coverageYear);
    }
  }

  function chooseYear(year: number) {
    setSelectedYear(year);
  }

  function retryLoad() {
    setError(null);
    setIsLoading(true);
    setReloadToken((value) => value + 1);
  }

  function handleYearKeyDown(
    event: React.KeyboardEvent<HTMLButtonElement>,
    currentIndex: number,
  ) {
    let nextIndex: number | null = null;

    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      nextIndex = Math.min(currentIndex + 1, filteredEditions.length - 1);
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      nextIndex = Math.max(currentIndex - 1, 0);
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = filteredEditions.length - 1;
    }

    if (nextIndex === null || nextIndex === currentIndex) return;
    event.preventDefault();
    const nextEdition = filteredEditions[nextIndex];
    setSelectedYear(nextEdition.coverageYear);
    yearButtonRefs.current[nextIndex]?.focus();
  }

  return (
    <>
      <SiteHeader />

      <main className={styles.page}>
        <section className={styles.hero} aria-labelledby="timeline-title">
          <div className={styles.heroTitle}>
            <p className={styles.eyebrow}>01 / 전체 시간축</p>
            <h1 id="timeline-title">
              서른일곱 해의 외교를
              <br />
              한 줄로 읽다
            </h1>
          </div>

          <div className={styles.heroNote}>
            <p>
              각 칸은 한 해의 외교백서가 다룬 <strong>대상연도</strong>입니다. 숫자는 원문에
              적힌 우선순위의 개수이며, 길이나 면적으로 중요도를 과장하지 않습니다.
            </p>
            <p className={styles.heroFootnote}>
              연도를 선택하면 배열 번호와 원문 출처를 함께 확인할 수 있습니다.
            </p>
          </div>

          <dl className={styles.ledger} aria-label="전체 자료 요약">
            <div>
              <dt>대상 범위</dt>
              <dd>
                {archive
                  ? `${archive.meta.coverage.from}—${archive.meta.coverage.to}`
                  : "1989—2025"}
              </dd>
            </div>
            <div>
              <dt>입력 우선순위</dt>
              <dd>{archive ? `${totalPriorityCount}개` : "—"}</dd>
            </div>
            <div>
              <dt>원문 대조 완료</dt>
              <dd>{archive ? `${verifiedCount} / ${editions.length}개년` : "—"}</dd>
            </div>
          </dl>
        </section>

        <section className={styles.explorer} aria-labelledby="explorer-title">
          <header className={styles.sectionHeader}>
            <div>
              <p className={styles.sectionNumber}>연도별 정책 배열 · 1989—2025</p>
              <h2 id="explorer-title">정부를 고르고, 해를 펼쳐보세요</h2>
            </div>
            <p className={styles.buildDate}>
              {archive ? `자료 생성일 ${archive.meta.builtAt}` : "자료를 불러오는 중"}
            </p>
          </header>

          <div className={styles.filterArea}>
            <span className={styles.filterLabel} id="government-filter-label">
              정부 필터
            </span>
            <div
              className={styles.filterList}
              role="group"
              aria-labelledby="government-filter-label"
            >
              <button
                type="button"
                className={styles.filterButton}
                data-active={administrationFilter === ALL_ADMINISTRATIONS}
                aria-pressed={administrationFilter === ALL_ADMINISTRATIONS}
                onClick={() => chooseAdministration(ALL_ADMINISTRATIONS)}
              >
                전체 <span>{editions.length || 28}년</span>
              </button>
              {administrations.map((administration) => {
                const count = editions.filter(
                  (edition) => edition.administration === administration,
                ).length;
                const active = administrationFilter === administration;
                return (
                  <button
                    key={administration}
                    type="button"
                    className={styles.filterButton}
                    data-active={active}
                    aria-pressed={active}
                    onClick={() => chooseAdministration(administration)}
                  >
                    {administration} <span>{count}년</span>
                  </button>
                );
              })}
            </div>
          </div>

          <div className={styles.statusLegend} aria-label="자료 상태 범례">
            {["verified", "partial", "blocked", "no-section"].map((status) => (
              <span key={status} data-status={status}>
                <b aria-hidden="true">{statusSymbol(status)}</b>
                {statusLabel(status)}
              </span>
            ))}
          </div>

          {isLoading ? (
            <div className={styles.loadingState} role="status">
              <span aria-hidden="true" />
              <p>외교백서 시간축을 불러오고 있습니다.</p>
            </div>
          ) : error ? (
            <div className={styles.errorState} role="alert">
              <p>{error}</p>
              <button type="button" onClick={retryLoad}>
                다시 불러오기
              </button>
            </div>
          ) : (
            <div className={styles.explorerLayout}>
              <section className={styles.timelinePanel} aria-label="연도 선택 시간축">
                <p className={styles.keyboardHint}>
                  <span aria-hidden="true">← →</span> 방향키로 앞뒤 연도를 이동할 수 있습니다.
                </p>

                <div className={styles.timelineRuns}>
                  {administrationGroups.map((group, groupIndex) => {
                    const firstYear = group.editions[0].coverageYear;
                    const lastYear = group.editions.at(-1)?.coverageYear ?? firstYear;
                    const priorityCount = group.editions.reduce(
                      (sum, edition) => sum + (prioritiesByYear.get(edition.coverageYear)?.length ?? 0),
                      0,
                    );

                    return (
                      <article className={styles.administrationRun} key={group.administration}>
                        <header className={styles.runHeader}>
                          <p className={styles.runIndex} aria-hidden="true">
                            {String(groupIndex + 1).padStart(2, "0")}
                          </p>
                          <h3>{group.administration} 정부</h3>
                          <p>{group.brand ?? "대한민국 정부"}</p>
                          <span>
                            {firstYear}—{lastYear} · 우선순위 {priorityCount}개
                          </span>
                        </header>

                        <div className={styles.yearGrid}>
                          {group.editions.map((edition) => {
                            const priorityCountForYear =
                              prioritiesByYear.get(edition.coverageYear)?.length ?? 0;
                            const active = edition.coverageYear === selectedYear;
                            const visibleIndex = visibleIndexByYear.get(edition.coverageYear) ?? 0;

                            return (
                              <button
                                key={edition.coverageYear}
                                ref={(element) => {
                                  yearButtonRefs.current[visibleIndex] = element;
                                }}
                                type="button"
                                className={styles.yearCard}
                                data-selected={active}
                                data-status={edition.status}
                                aria-pressed={active}
                                aria-controls="year-detail"
                                aria-label={`${edition.coverageYear}년, ${edition.administration} 정부, 우선순위 ${priorityCountForYear}개, ${statusLabel(edition.status)}`}
                                aria-keyshortcuts="ArrowLeft ArrowRight ArrowUp ArrowDown Home End"
                                onClick={() => chooseYear(edition.coverageYear)}
                                onKeyDown={(event) => handleYearKeyDown(event, visibleIndex)}
                              >
                                <span className={styles.cardStatus}>
                                  <b aria-hidden="true">{statusSymbol(edition.status)}</b>
                                  {statusLabel(edition.status)}
                                </span>
                                <strong className={styles.cardYear}>{edition.coverageYear}</strong>
                                <span className={styles.cardEdition}>{edition.title}</span>
                                <span className={styles.cardBottom}>
                                  <span>{edition.administration} 정부</span>
                                  <span>
                                    <b>{priorityCountForYear}</b>개 항목
                                  </span>
                                </span>
                              </button>
                            );
                          })}
                        </div>
                      </article>
                    );
                  })}
                </div>
              </section>

              <aside
                className={styles.detailPanel}
                id="year-detail"
                aria-labelledby="selected-year-title"
                aria-live="polite"
              >
                {selectedEdition ? (
                  <>
                    <div className={styles.detailLead}>
                      <div>
                        <p>선택한 대상연도</p>
                        <p className={styles.detailYear}>{selectedEdition.coverageYear}</p>
                      </div>
                      <span className={styles.detailStatus} data-status={selectedEdition.status}>
                        <b aria-hidden="true">{statusSymbol(selectedEdition.status)}</b>
                        {statusLabel(selectedEdition.status)}
                      </span>
                    </div>

                    <p className={styles.detailKicker}>
                      {selectedEdition.administration} 정부 · {selectedEdition.title}
                    </p>
                    <h2 id="selected-year-title">
                      {selectedEdition.section.label ??
                        `${selectedEdition.coverageYear}년도 외교정책 우선순위`}
                    </h2>

                    <dl className={styles.editionFacts}>
                      <div>
                        <dt>발간분</dt>
                        <dd>
                          {selectedEdition.title} ({selectedEdition.publishedYear})
                        </dd>
                      </div>
                      <div>
                        <dt>원문 위치</dt>
                        <dd>{formatSection(selectedEdition)}</dd>
                      </div>
                      <div>
                        <dt>번호 형식</dt>
                        <dd>{markStyleLabel(selectedEdition.markStyle)}</dd>
                      </div>
                    </dl>

                    {selectedEdition.coverageYear === 2025 && (
                      <Link className={styles.analysisLink} href="/years/2025">
                        2025년 원문 데이터 분석 보기 <span aria-hidden="true">→</span>
                      </Link>
                    )}

                    <section className={styles.sourceBlock} aria-labelledby="source-title">
                      <h3 id="source-title">원문 파일</h3>
                      {selectedEdition.sourceFiles.length ? (
                        <ul>
                          {selectedEdition.sourceFiles.map((sourceFile) => (
                            <li key={sourceFile}>{sourceFile}</li>
                          ))}
                        </ul>
                      ) : (
                        <p>등록된 원문 파일이 없습니다.</p>
                      )}
                    </section>

                    {selectedEdition.note && (
                      <p className={styles.reviewNote}>
                        <strong>검수 메모</strong>
                        {selectedEdition.note}
                      </p>
                    )}

                    <section className={styles.prioritySection} aria-labelledby="priority-title">
                      <header>
                        <h3 id="priority-title">원문 배열 순서</h3>
                        <span>{selectedPriorities.length}개 항목</span>
                      </header>

                      {selectedPriorities.length ? (
                        <ol>
                          {selectedPriorities.map((priority) => (
                            <li key={priority.id} value={priority.ordinal}>
                              <span className={styles.ordinal} aria-hidden="true">
                                {String(priority.ordinal).padStart(2, "0")}
                              </span>
                              <div>
                                <h4>{priority.title}</h4>
                                <p className={styles.priorityMeta}>
                                  {streamLabels.get(priority.stream) ?? priority.stream}
                                  <span aria-hidden="true"> · </span>
                                  배열 근거 {priority.ordinalSource || "확인 중"}
                                </p>
                                <p className={styles.prioritySource}>
                                  {formatPrioritySource(priority)}
                                </p>
                                {priority.flags.length > 0 && (
                                  <div className={styles.flagList} aria-label="자료 주의사항">
                                    {priority.flags.map((flag) => (
                                      <span key={flag}>{flagLabel(flag)}</span>
                                    ))}
                                  </div>
                                )}
                              </div>
                            </li>
                          ))}
                        </ol>
                      ) : (
                        <div className={styles.emptyPriorities}>
                          <p>입력된 우선순위 항목이 없습니다.</p>
                          <span>
                            이는 정책이 없었다는 뜻이 아니라, 원문 결손 또는 별도 기조 절이 없음을
                            표시합니다.
                          </span>
                        </div>
                      )}
                    </section>
                  </>
                ) : (
                  <p className={styles.noSelection}>시간축에서 연도를 선택해 주세요.</p>
                )}
              </aside>
            </div>
          )}
        </section>

        <section className={styles.methodNote} aria-labelledby="method-title">
          <p className={styles.sectionNumber}>읽는 법</p>
          <div>
            <h2 id="method-title">순서는 기록하고, 공백은 숨기지 않습니다.</h2>
            <p>
              카드의 숫자는 백서에서 확인된 항목 수입니다. 우선순위 번호는 막대 길이로 바꾸지
              않고 원문 순서 그대로 나열합니다. 0개인 해도 시간축에서 지우지 않아 자료의 부재와
              정책의 부재를 구별합니다.
            </p>
          </div>
        </section>
      </main>

      <SiteFooter />
    </>
  );
}
