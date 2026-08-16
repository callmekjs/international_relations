"use client";

import { useEffect, useMemo, useState } from "react";
import { SiteFooter, SiteHeader } from "../../../components/SiteHeader";
import styles from "./year-analysis.module.css";

type Priority = {
  id: string;
  ordinal: number;
  title: string;
  streamId: string;
  streamLabel: string;
  characters: number | null;
  words: number | null;
  wordShare: number | null;
  quote: string;
  source: {
    edition: string;
    chapter: number;
    section: number;
    page: number | null;
  };
  flags: string[];
};

type Actor = {
  id: string;
  label: string;
  variants: string;
  policySection: number;
  fullDocument: number;
};

type Analysis = {
  meta: {
    coverageYear: number;
    title: string;
    publishedYear: number;
    administration: string;
    status: string;
    sourceFile: string;
    sourcePath: string;
    extractionPath: string;
    sourceMegabytes: number;
    pageCount: number | null;
    chapter: number;
    section: number;
    sectionLabel: string;
    externalDataUsed: boolean;
  };
  summary: {
    priorityCount: number;
    priorityBodyWords: number;
    topThreeWordShare: number;
    policySectionCharacters: number;
    documentCharacters: number;
    longestPriorityId: string | null;
  };
  priorities: Priority[];
  actors: Actor[];
  concepts: { label: string; count: number }[];
  methodology: {
    actorUnit: string;
    lengthUnit: string;
    policyScope: string;
    documentScope: string;
    cautions: string[];
  };
};

type ActorScope = "policySection" | "fullDocument";

const statusLabel: Record<string, string> = {
  verified: "원문 대조 완료",
};

function number(value: number) {
  return value.toLocaleString("ko-KR");
}

export default function Year2025AnalysisPage() {
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedPriorityId, setSelectedPriorityId] = useState<string | null>(null);
  const [actorScope, setActorScope] = useState<ActorScope>("policySection");

  useEffect(() => {
    const controller = new AbortController();

    fetch("/analysis-2025.json", { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("2025년 분석 자료를 불러오지 못했습니다.");
        return response.json() as Promise<Analysis>;
      })
      .then((data) => {
        setAnalysis(data);
        setSelectedPriorityId(data.summary.longestPriorityId ?? data.priorities[0]?.id ?? null);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "2025년 분석 자료를 불러오지 못했습니다.");
      });

    return () => controller.abort();
  }, []);

  const selectedPriority = useMemo(
    () => analysis?.priorities.find((priority) => priority.id === selectedPriorityId) ?? null,
    [analysis, selectedPriorityId],
  );

  const longestPriority = useMemo(
    () => analysis?.priorities.find((priority) => priority.id === analysis.summary.longestPriorityId) ?? null,
    [analysis],
  );

  const maxPriorityWords = useMemo(
    () => Math.max(1, ...(analysis?.priorities.map((priority) => priority.words ?? 0) ?? [1])),
    [analysis],
  );

  const actorRows = useMemo(() => {
    if (!analysis) return [];
    return [...analysis.actors].sort(
      (left, right) => right[actorScope] - left[actorScope] || left.label.localeCompare(right.label, "ko"),
    );
  }, [actorScope, analysis]);

  const maxActorCount = Math.max(1, ...actorRows.map((actor) => actor[actorScope]));

  return (
    <div className={styles.page}>
      <SiteHeader />

      <main className={styles.main}>
        <section className={styles.hero} aria-labelledby="analysis-title">
          <div className={styles.heroYear} aria-hidden="true">2025</div>
          <div className={styles.heroCopy}>
            <p className={styles.kicker}>SINGLE-YEAR ANALYSIS · 외부 데이터 0건</p>
            <h1 id="analysis-title">한 해의 외교를<br />원문 안에서 읽다</h1>
            <p>
              「2025년도 국제정세와 외교활동」 한 권에서 정책의 배열, 항목별 서술량,
              주요 행위자와 핵심어 출현을 계산했습니다. 결과와 근거 문장을 같은 화면에서 확인할 수 있습니다.
            </p>
          </div>
          <aside className={styles.heroFinding} aria-labelledby="finding-title">
            <p>가장 먼저 보이는 차이</p>
            <h2 id="finding-title">첫 번째 항목과<br />가장 길게 쓴 항목은 달랐습니다.</h2>
            <dl>
              <div>
                <dt>배열 1번</dt>
                <dd>{analysis?.priorities[0]?.title ?? "분석 중"}</dd>
              </div>
              <div>
                <dt>본문 최장</dt>
                <dd>{longestPriority?.title ?? "분석 중"}</dd>
              </div>
            </dl>
          </aside>
        </section>

        {error ? (
          <section className={styles.state} role="alert">
            <h2>분석 결과를 표시할 수 없습니다.</h2>
            <p>{error}</p>
          </section>
        ) : !analysis ? (
          <div className={styles.state} role="status">2025년 원문 분석 결과를 불러오고 있습니다.</div>
        ) : (
          <>
            <dl className={styles.stats} aria-label="2025년 분석 자료 요약">
              <div>
                <dt>원본 PDF</dt>
                <dd>{analysis.meta.pageCount ?? "—"}<span>쪽</span></dd>
                <small>{analysis.meta.sourceMegabytes} MB</small>
              </div>
              <div>
                <dt>정책 기조</dt>
                <dd>{analysis.summary.priorityCount}<span>개</span></dd>
                <small>인쇄된 1–7번</small>
              </div>
              <div>
                <dt>항목 본문</dt>
                <dd>{number(analysis.summary.priorityBodyWords)}<span>어절</span></dd>
                <small>제목·반복 머리글 제외</small>
              </div>
              <div>
                <dt>외부 데이터</dt>
                <dd>{analysis.meta.externalDataUsed ? "사용" : "0"}<span>건</span></dd>
                <small>2025 백서만 분석</small>
              </div>
            </dl>

            <section className={styles.prioritySection} aria-labelledby="priority-analysis-title">
              <header className={styles.sectionHeader}>
                <div>
                  <p className={styles.sectionNumber}>01 / 배열과 서술량</p>
                  <h2 id="priority-analysis-title">순서는 그대로,<br />분량은 따로 봅니다</h2>
                </div>
                <p>
                  번호는 백서의 배열 순서입니다. 막대는 각 항목 본문의 어절 수만 나타냅니다.
                  상위 세 항목이 전체 항목 본문의 {analysis.summary.topThreeWordShare}%를 차지합니다.
                </p>
              </header>

              <div className={styles.priorityLayout}>
                <ol className={styles.priorityList}>
                  {analysis.priorities.map((priority) => {
                    const active = priority.id === selectedPriorityId;
                    const barWidth = ((priority.words ?? 0) / maxPriorityWords) * 100;
                    return (
                      <li key={priority.id}>
                        <button
                          type="button"
                          className={active ? styles.activePriority : undefined}
                          aria-pressed={active}
                          onClick={() => setSelectedPriorityId(priority.id)}
                        >
                          <span className={styles.ordinal}>{String(priority.ordinal).padStart(2, "0")}</span>
                          <span className={styles.priorityCopy}>
                            <strong>{priority.title}</strong>
                            <small>{priority.streamLabel}</small>
                            <span className={styles.lengthTrack} aria-hidden="true">
                              <span style={{ width: `${barWidth}%` }} />
                            </span>
                          </span>
                          <span className={styles.priorityMeasure}>
                            <strong>{priority.words === null ? "—" : number(priority.words)}</strong>
                            <small>어절 · {priority.wordShare ?? 0}%</small>
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ol>

                <aside className={styles.evidence} aria-live="polite">
                  {selectedPriority ? (
                    <>
                      <p className={styles.evidenceKicker}>
                        {String(selectedPriority.ordinal).padStart(2, "0")} · {selectedPriority.streamLabel}
                      </p>
                      <h3>{selectedPriority.title}</h3>
                      <blockquote>{selectedPriority.quote}</blockquote>
                      <dl>
                        <div>
                          <dt>본문 분량</dt>
                          <dd>{selectedPriority.words === null ? "확인 중" : `${number(selectedPriority.words)}어절 · ${selectedPriority.wordShare}%`}</dd>
                        </div>
                        <div>
                          <dt>원문 위치</dt>
                          <dd>제{selectedPriority.source.chapter}장 · 제{selectedPriority.source.section}절 · {selectedPriority.source.page ? `${selectedPriority.source.page}쪽` : "쪽수 확인 중"}</dd>
                        </div>
                        <div>
                          <dt>근거 상태</dt>
                          <dd>{selectedPriority.flags.includes("heading-only") ? "제목으로 확인" : statusLabel[analysis.meta.status] ?? analysis.meta.status}</dd>
                        </div>
                      </dl>
                    </>
                  ) : (
                    <p>왼쪽 항목을 선택하면 원문 근거가 표시됩니다.</p>
                  )}
                </aside>
              </div>
            </section>

            <section className={styles.actorSection} aria-labelledby="actor-title">
              <header className={styles.sectionHeader}>
                <div>
                  <p className={styles.sectionNumber}>02 / 행위자 표기</p>
                  <h2 id="actor-title">누구를 얼마나<br />자주 불렀나</h2>
                </div>
                <div className={styles.scopeControl} role="group" aria-label="행위자 집계 범위">
                  <button
                    type="button"
                    aria-pressed={actorScope === "policySection"}
                    onClick={() => setActorScope("policySection")}
                  >
                    기조절만
                  </button>
                  <button
                    type="button"
                    aria-pressed={actorScope === "fullDocument"}
                    onClick={() => setActorScope("fullDocument")}
                  >
                    백서 전체
                  </button>
                </div>
              </header>

              <div className={styles.actorChart}>
                {actorRows.map((actor, index) => (
                  <div className={styles.actorRow} key={actor.id}>
                    <span className={styles.actorRank}>{String(index + 1).padStart(2, "0")}</span>
                    <span className={styles.actorLabel}>
                      <strong>{actor.label}</strong>
                      <small>{actor.variants}</small>
                    </span>
                    <span className={styles.actorTrack} aria-hidden="true">
                      <span style={{ width: `${(actor[actorScope] / maxActorCount) * 100}%` }} />
                    </span>
                    <strong className={styles.actorCount}>{number(actor[actorScope])}<small>회</small></strong>
                  </div>
                ))}
              </div>
              <p className={styles.chartNote}>
                선택한 표기와 결합어를 합산한 단순 출현 횟수입니다. 같은 단어라도 문맥의 찬반이나 중요도는 판정하지 않습니다.
              </p>
            </section>

            <section className={styles.conceptSection} aria-labelledby="concept-title">
              <header className={styles.sectionHeader}>
                <div>
                  <p className={styles.sectionNumber}>03 / 기조의 언어</p>
                  <h2 id="concept-title">정책 기조를 만든<br />반복 어휘</h2>
                </div>
                <p>제1장 제2절 안에서 지정한 핵심어가 몇 차례 나타나는지 셌습니다. ‘협력’이 39회로 가장 많습니다.</p>
              </header>

              <ol className={styles.conceptGrid}>
                {analysis.concepts.map((concept, index) => (
                  <li key={concept.label}>
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <strong>{concept.label}</strong>
                    <b>{concept.count}<small>회</small></b>
                  </li>
                ))}
              </ol>
            </section>

            <aside className={styles.method} aria-labelledby="method-title">
              <div>
                <p className={styles.sectionNumber}>04 / 분석 범위</p>
                <h2 id="method-title">한 권 밖으로 나가지 않았습니다</h2>
              </div>
              <div className={styles.methodBody}>
                <p>
                  <strong>원본</strong> {analysis.meta.sourceFile} · {analysis.meta.publishedYear}년 발간 · {statusLabel[analysis.meta.status] ?? analysis.meta.status}
                </p>
                <p>
                  <strong>분석 단위</strong> {analysis.methodology.lengthUnit}. 행위자는 {analysis.methodology.actorUnit}로 집계했습니다.
                </p>
                <ul>
                  {analysis.methodology.cautions.map((caution) => <li key={caution}>{caution}</li>)}
                </ul>
                <div className={styles.dataLinks}>
                  <a href="/analysis-2025.json" download>분석 JSON 내려받기 ↓</a>
                  <a href="/data.json" download>우선순위 원자료 보기 ↗</a>
                </div>
              </div>
            </aside>
          </>
        )}
      </main>

      <SiteFooter />
    </div>
  );
}
