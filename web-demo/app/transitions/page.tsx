"use client";

import { useEffect, useMemo, useState } from "react";
import { SiteFooter, SiteHeader } from "../../components/SiteHeader";
import styles from "./transitions.module.css";

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

type Transition = {
  id: string;
  previous: Edition;
  next: Edition;
};

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

function findTransitions(editions: Edition[]): Transition[] {
  const sorted = [...editions].sort((a, b) => a.coverageYear - b.coverageYear);
  const transitions: Transition[] = [];

  for (let index = 1; index < sorted.length; index += 1) {
    const previous = sorted[index - 1];
    const next = sorted[index];
    if (previous.administration === next.administration) continue;

    transitions.push({
      id: `${previous.coverageYear}-${next.coverageYear}-${previous.administration}-${next.administration}`,
      previous,
      next,
    });
  }

  return transitions;
}

function locationLabel(edition: Edition) {
  const parts = [
    edition.section.chapter ? `제${edition.section.chapter}장` : null,
    edition.section.section ? `제${edition.section.section}절` : null,
    edition.section.page ? `${edition.section.page}쪽` : null,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "위치 정보 확인 중";
}

function PriorityColumn({
  edition,
  priorities,
  side,
}: {
  edition: Edition;
  priorities: Priority[];
  side: "previous" | "next";
}) {
  return (
    <article className={`${styles.comparisonColumn} ${styles[side]}`}>
      <header className={styles.columnHeader}>
        <div>
          <p className={styles.sideLabel}>{side === "previous" ? "전임 정부 마지막 대상연도" : "신임 정부 첫 대상연도"}</p>
          <h2>
            <span>{edition.coverageYear}</span>
            {edition.administration} 정부
          </h2>
        </div>
        <span className={`${styles.status} ${statusClass(edition.status)}`}>
          {statusLabel(edition.status)}
        </span>
      </header>

      <dl className={styles.editionMeta}>
        <div>
          <dt>발간분</dt>
          <dd>{edition.title}</dd>
        </div>
        <div>
          <dt>원문 위치</dt>
          <dd>{locationLabel(edition)}</dd>
        </div>
        {edition.brand && (
          <div>
            <dt>정부 표기</dt>
            <dd>{edition.brand}</dd>
          </div>
        )}
      </dl>

      <div className={styles.priorityHeading}>
        <h3>백서의 배열 순서</h3>
        <span>{priorities.length ? `${priorities.length}개 확인` : "확인된 항목 없음"}</span>
      </div>

      {priorities.length ? (
        <ol className={styles.priorityList}>
          {priorities.map((priority) => (
            <li key={priority.id}>
              <span className={styles.ordinal} aria-label={`${priority.ordinal}번`}>
                {priority.ordinal}
              </span>
              <div>
                <p>{priority.title}</p>
                <small>배열 근거: {priority.ordinalSource || "확인 중"}</small>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <div className={styles.emptyPriorities}>
          <strong>{statusLabel(edition.status)}</strong>
          <p>{edition.note ?? "이 판본에서 확인된 외교정책 기조 항목이 없습니다."}</p>
        </div>
      )}

      {edition.note && priorities.length > 0 && (
        <details className={styles.note}>
          <summary>자료 검수 메모</summary>
          <p>{edition.note.replaceAll("**", "")}</p>
        </details>
      )}
    </article>
  );
}

export default function TransitionsPage() {
  const [archive, setArchive] = useState<ArchiveData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

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

  const transitions = useMemo(
    () => findTransitions(archive?.editions ?? []),
    [archive],
  );

  const selected = transitions.find((transition) => transition.id === selectedId) ?? transitions[0] ?? null;

  const previousPriorities = useMemo(
    () =>
      (archive?.priorities ?? [])
        .filter((priority) => priority.coverageYear === selected?.previous.coverageYear)
        .sort((a, b) => a.ordinal - b.ordinal),
    [archive, selected],
  );

  const nextPriorities = useMemo(
    () =>
      (archive?.priorities ?? [])
        .filter((priority) => priority.coverageYear === selected?.next.coverageYear)
        .sort((a, b) => a.ordinal - b.ordinal),
    [archive, selected],
  );

  return (
    <div className={styles.page}>
      <SiteHeader />
      <main className={styles.main}>
        <section className={styles.hero} aria-labelledby="transitions-title">
          <div>
            <p className={styles.kicker}>정권 이음매 · TRANSITIONS</p>
            <h1 id="transitions-title">바뀌기 직전과<br />바뀐 뒤의 배열</h1>
          </div>
          <div className={styles.heroNote}>
            <p>
              외교백서가 전임 정부의 마지막 대상연도와 신임 정부의 첫 대상연도에
              정책 항목을 어떤 순서로 놓았는지 나란히 읽습니다.
            </p>
            <p><strong>이 비교는 정권 교체가 변화를 일으켰다고 주장하지 않습니다.</strong></p>
          </div>
        </section>

        {error ? (
          <div className={styles.error} role="alert">
            <h2>자료를 표시할 수 없습니다.</h2>
            <p>{error}</p>
          </div>
        ) : !archive ? (
          <div className={styles.loading} role="status">정권 변화 지점을 계산하고 있습니다.</div>
        ) : (
          <>
            <section className={styles.selectorSection} aria-labelledby="selector-title">
              <div className={styles.sectionLead}>
                <div>
                  <p className={styles.sectionNumber}>01 / 이음매 선택</p>
                  <h2 id="selector-title">{transitions.length}개의 정권 변화 지점</h2>
                </div>
                <p>외교백서의 대상연도와 정부 표기가 바뀌는 지점을 데이터에서 자동으로 찾았습니다.</p>
              </div>

              <ul className={styles.transitionSelector} aria-label="비교할 정권 이음매 선택">
                {transitions.map((transition, index) => {
                  const active = transition.id === selected?.id;
                  return (
                    <li key={transition.id}>
                      <button
                        type="button"
                        className={active ? styles.active : undefined}
                        aria-pressed={active}
                        onClick={() => setSelectedId(transition.id)}
                      >
                        <span className={styles.selectorIndex}>{String(index + 1).padStart(2, "0")}</span>
                        <strong>{transition.previous.administration} → {transition.next.administration}</strong>
                        <small>{transition.previous.coverageYear} / {transition.next.coverageYear}</small>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </section>

            {selected && (
              <section className={styles.comparisonSection} aria-labelledby="comparison-title">
                <div className={styles.comparisonTitle}>
                  <div>
                    <p className={styles.sectionNumber}>02 / 나란히 읽기</p>
                    <h2 id="comparison-title">
                      {selected.previous.administration}에서 {selected.next.administration}으로
                    </h2>
                  </div>
                  <p>큰 숫자는 점수나 수량이 아니라 각 백서에 나타난 배열 위치입니다.</p>
                </div>

                <div className={styles.comparisonGrid}>
                  <PriorityColumn
                    edition={selected.previous}
                    priorities={previousPriorities}
                    side="previous"
                  />
                  <PriorityColumn
                    edition={selected.next}
                    priorities={nextPriorities}
                    side="next"
                  />
                </div>
              </section>
            )}

            <aside className={styles.caution} aria-labelledby="caution-title">
              <p className={styles.sectionNumber}>03 / 비교 전 주의</p>
              <h2 id="caution-title">교체연도는 취임일로 잘린 한 해가 아닙니다.</h2>
              <div>
                <p>
                  백서의 대상연도는 달력연도 단위이므로 신임 정부의 첫 대상연도에
                  정권 교체 전 기간의 외교활동이 함께 포함될 수 있습니다.
                </p>
                <p>
                  판본마다 숫자·순서말·표·산문 등 배열 표기가 다릅니다. 여기서는
                  확인된 문서 순서만 옮기며, 위치 변화의 원인이나 정책 성과를 설명하지 않습니다.
                </p>
              </div>
            </aside>
          </>
        )}
      </main>
      <SiteFooter />
    </div>
  );
}
