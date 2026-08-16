"use client";

import { useEffect, useMemo, useState } from "react";
import { SiteFooter, SiteHeader } from "@/components/SiteHeader";

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
  note: string;
  members: string[];
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

const TARGET_ADMINISTRATION = "노무현";

const streamColors: Record<string, string> = {
  peninsula: "#7b5268",
  neighbors: "#4f7480",
  regional: "#6f7955",
  economy: "#a05b3d",
  "global-role": "#8a6b35",
  "overseas-koreans": "#4e6f66",
  "public-diplomacy": "#8b5a4f",
  capacity: "#5f5d72",
  iraq: "#8b633d",
};

const yearCoordinates = [
  { x: 210, y: 98 },
  { x: 350, y: 174 },
  { x: 398, y: 310 },
  { x: 350, y: 446 },
  { x: 210, y: 522 },
];

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    verified: "원문 대조 완료",
    partial: "일부 확인",
    "from-preface": "발간사 대체",
    pending: "검수 진행 중",
    blocked: "원본 확인 불가",
  };
  return labels[status] ?? status;
}

function flagLabel(flag: string) {
  const labels: Record<string, string> = {
    partial: "일부 확인",
    ocr: "OCR",
    "heading-only": "제목만 확인",
    "lead-only": "리드 문장 확인",
    "from-preface": "발간사 대체",
    "title-lost": "제목 유실",
  };
  return labels[flag] ?? flag;
}

function markStyleLabel(markStyle: string | null | undefined) {
  const labels: Record<string, string> = {
    bullet: "불릿 기호",
    circled: "원문자 번호(①·②…)",
    heading: "표·소제목 배열",
    "inline-lead": "문단 첫머리",
    number: "아라비아 숫자",
    "ordinal-word": "순서말(첫째·둘째…)",
    prose: "서술 순서",
    roman: "로마 숫자(Ⅰ·Ⅱ…)",
  };
  return markStyle ? (labels[markStyle] ?? markStyle) : "형식 확인 중";
}

function yearCountLabel(edition: Edition, count: number) {
  if (!count) return "항목 확인 중";
  return edition.status === "partial" ? `${count}개 확인 · 일부` : `${count}개 항목`;
}

function expectedPriorityCount(edition: Edition | null, priorities: Priority[]) {
  const maximumOrdinal = priorities.reduce((maximum, item) => Math.max(maximum, item.ordinal), 0);
  const documentedCount = edition?.note?.match(/(\d+)\s*개\s*(?:기둥|분야|목표|항목)/)?.[1];
  return Math.max(maximumOrdinal, documentedCount ? Number(documentedCount) : 0);
}

function splitLabel(text: string, firstLimit = 17, secondLimit = 19) {
  if (text.length <= firstLimit) return [text];
  const first = text.slice(0, firstLimit);
  const rest = text.slice(firstLimit);
  const second = rest.length > secondLimit ? `${rest.slice(0, secondLimit - 1)}…` : rest;
  return [first, second];
}

function citationText(priority: Priority) {
  const chapter = priority.source.chapter ? `제${priority.source.chapter}장` : "장 미상";
  const section = priority.source.section ? `제${priority.source.section}절` : "절 미상";
  const page = priority.source.page ? `${priority.source.page}쪽` : "쪽수 확인 중";
  return `${priority.source.edition}, ${chapter} ${section}, ${page}. “${priority.quote}”`;
}

export default function RohGovernmentPage() {
  const [archive, setArchive] = useState<ArchiveData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedYear, setSelectedYear] = useState(2003);
  const [selectedPriorityId, setSelectedPriorityId] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let active = true;
    fetch("/data.json")
      .then((response) => {
        if (!response.ok) throw new Error("자료를 불러오지 못했습니다.");
        return response.json() as Promise<ArchiveData>;
      })
      .then((data) => {
        if (!active) return;
        setArchive(data);
        const first = data.priorities
          .filter((item) => item.coverageYear === 2003)
          .sort((a, b) => a.ordinal - b.ordinal)[0];
        setSelectedPriorityId(first?.id ?? null);
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : "자료를 불러오지 못했습니다.");
      });
    return () => {
      active = false;
    };
  }, []);

  const editions = useMemo(
    () =>
      (archive?.editions ?? [])
        .filter((edition) => edition.administration === TARGET_ADMINISTRATION)
        .sort((a, b) => a.coverageYear - b.coverageYear),
    [archive],
  );

  const selectedEdition = editions.find((edition) => edition.coverageYear === selectedYear) ?? null;

  const selectedYearPriorities = useMemo(
    () =>
      (archive?.priorities ?? [])
        .filter((priority) => priority.coverageYear === selectedYear)
        .sort((a, b) => a.ordinal - b.ordinal),
    [archive, selectedYear],
  );

  const selectedPriority =
    selectedYearPriorities.find((priority) => priority.id === selectedPriorityId) ??
    selectedYearPriorities[0] ??
    null;

  const prioritySlotCount = expectedPriorityCount(selectedEdition, selectedYearPriorities);
  const missingOrdinals = Array.from({ length: prioritySlotCount }, (_, index) => index + 1).filter(
    (ordinal) => !selectedYearPriorities.some((priority) => priority.ordinal === ordinal),
  );

  const selectedStream = selectedPriority
    ? archive?.streams.find((stream) => stream.id === selectedPriority.stream) ?? null
    : null;

  const filledYears = editions.filter((edition) =>
    archive?.priorities.some((priority) => priority.coverageYear === edition.coverageYear),
  ).length;

  function chooseYear(year: number) {
    setSelectedYear(year);
    const first = archive?.priorities
      .filter((priority) => priority.coverageYear === year)
      .sort((a, b) => a.ordinal - b.ordinal)[0];
    setSelectedPriorityId(first?.id ?? null);
    setCopied(false);
  }

  function choosePriority(id: string) {
    setSelectedPriorityId(id);
    setCopied(false);
  }

  async function copyCitation() {
    if (!selectedPriority) return;
    await navigator.clipboard.writeText(citationText(selectedPriority));
    setCopied(true);
  }

  const priorityY = (index: number, total: number) => {
    if (total <= 1) return 310;
    const top = total >= 7 ? 58 : 100;
    const bottom = total >= 7 ? 562 : 520;
    return top + (index * (bottom - top)) / (total - 1);
  };

  return (
    <div className="government-page">
      <SiteHeader />

      <div className="archive-shell">

      <main>
        <section className="subpage-intro" aria-labelledby="intro-title">
          <div>
            <p className="eyebrow">정부별 그래프 / 노무현 정부</p>
            <h1 id="intro-title">노무현 정부의 외교정책 가지</h1>
          </div>
          <div className="subpage-intro-note">
            <p>
              가운데 정부에서 대상연도로, 다시 그해 백서의 우선순위로 가지를 펼칩니다.
              숫자는 외교백서에 적힌 배열 순서이며, 선은 인과관계를 뜻하지 않습니다.
            </p>
            <a href="#evidence">원문 근거까지 읽기 ↓</a>
          </div>
        </section>

        <section className="graph-section" aria-labelledby="graph-title">
          <div className="section-heading">
            <div>
              <p className="section-number">01 / 정부에서 연도로</p>
              <h2 id="graph-title">대상연도에서 우선순위로</h2>
            </div>
            <p className="data-state">
              {archive ? `${editions.length}개 대상연도 · ${filledYears}개 연도 항목 입력` : "자료 불러오는 중"}
            </p>
          </div>

          {error ? (
            <div className="error-message" role="alert">{error}</div>
          ) : (
            <div className="graph-layout">
              <div className="graph-column">
                <div className="year-selector" aria-label="대상연도 선택">
                  {editions.map((edition) => {
                    const count = archive?.priorities.filter(
                      (priority) => priority.coverageYear === edition.coverageYear,
                    ).length ?? 0;
                    return (
                      <button
                        key={edition.coverageYear}
                        type="button"
                        className={edition.coverageYear === selectedYear ? "is-active" : ""}
                        aria-pressed={edition.coverageYear === selectedYear}
                        onClick={() => chooseYear(edition.coverageYear)}
                      >
                        <span>{edition.coverageYear}</span>
                        <small>{yearCountLabel(edition, count)}</small>
                      </button>
                    );
                  })}
                </div>

                <svg
                  className="knowledge-graph"
                  viewBox="0 0 920 620"
                  role="group"
                  aria-labelledby="graph-svg-title graph-svg-description"
                >
                  <title id="graph-svg-title">노무현 정부 중심 외교정책 지식 그래프</title>
                  <desc id="graph-svg-description">
                    노무현 정부에서 2003년부터 2007년 대상연도로 연결되고, 선택한 연도의 외교정책 우선순위가 오른쪽으로 펼쳐집니다.
                  </desc>

                  <g className="government-edges" aria-hidden="true">
                    {editions.map((edition, index) => {
                      const point = yearCoordinates[index];
                      if (!point) return null;
                      return <line key={edition.coverageYear} x1="174" y1="310" x2={point.x} y2={point.y} />;
                    })}
                  </g>

                  {selectedEdition && (() => {
                    const selectedIndex = editions.findIndex(
                      (edition) => edition.coverageYear === selectedEdition.coverageYear,
                    );
                    const point = yearCoordinates[selectedIndex];
                    if (!point) return null;
                    if (!selectedYearPriorities.length) {
                      return (
                        <g className="empty-branch" aria-hidden="true">
                          <line x1={point.x} y1={point.y} x2="590" y2="310" />
                          <rect x="536" y="280" width="132" height="60" rx="3" />
                          <text x="602" y="305" textAnchor="middle">항목 데이터</text>
                          <text x="602" y="324" textAnchor="middle">확인 중</text>
                        </g>
                      );
                    }
                    return (
                      <g className="priority-edges" aria-hidden="true">
                        {selectedYearPriorities.map((priority) => {
                          const y = priorityY(priority.ordinal - 1, prioritySlotCount);
                          return (
                            <line
                              key={priority.id}
                              className={priority.id === selectedPriority?.id ? "is-selected" : ""}
                              x1={point.x}
                              y1={point.y}
                              x2="520"
                              y2={y}
                            />
                          );
                        })}
                        {missingOrdinals.map((ordinal) => (
                          <line
                            key={`missing-${ordinal}`}
                            className="is-missing"
                            x1={point.x}
                            y1={point.y}
                            x2="520"
                            y2={priorityY(ordinal - 1, prioritySlotCount)}
                          />
                        ))}
                      </g>
                    );
                  })()}

                  <g
                    className="government-node"
                    role="img"
                    aria-label="중심 노드, 노무현 정부"
                  >
                    <circle cx="130" cy="310" r="69" />
                    <text x="130" y="299" textAnchor="middle">노무현</text>
                    <text x="130" y="323" textAnchor="middle">정부</text>
                    <text className="node-caption" x="130" y="347" textAnchor="middle">2003–2007 대상연도</text>
                  </g>

                  {editions.map((edition, index) => {
                    const point = yearCoordinates[index];
                    if (!point) return null;
                    const count = archive?.priorities.filter(
                      (priority) => priority.coverageYear === edition.coverageYear,
                    ).length ?? 0;
                    const active = edition.coverageYear === selectedYear;
                    return (
                      <g
                        key={edition.coverageYear}
                        className={`year-node ${active ? "is-selected" : ""} ${count ? "" : "is-empty"}`}
                        role="button"
                        tabIndex={0}
                        aria-label={`${edition.coverageYear}년, ${edition.title}, ${yearCountLabel(edition, count)}`}
                        aria-pressed={active}
                        onClick={() => chooseYear(edition.coverageYear)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            chooseYear(edition.coverageYear);
                          }
                        }}
                      >
                        <circle cx={point.x} cy={point.y} r={active ? 43 : 36} />
                        <text x={point.x} y={point.y + 5} textAnchor="middle">{edition.coverageYear}</text>
                        <text className="node-caption" x={point.x} y={point.y + 58} textAnchor="middle">
                          {yearCountLabel(edition, count)}
                        </text>
                      </g>
                    );
                  })}

                  {selectedYearPriorities.map((priority) => {
                    const y = priorityY(priority.ordinal - 1, prioritySlotCount);
                    const selected = priority.id === selectedPriority?.id;
                    const lines = splitLabel(priority.title);
                    const color = streamColors[priority.stream] ?? "#6e685b";
                    return (
                      <g
                        key={priority.id}
                        className={`priority-node ${selected ? "is-selected" : ""}`}
                        role="button"
                        tabIndex={0}
                        aria-label={`${selectedYear}년 ${priority.ordinal}번, ${priority.title}`}
                        aria-pressed={selected}
                        onClick={() => choosePriority(priority.id)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            choosePriority(priority.id);
                          }
                        }}
                      >
                        <rect
                          x="520"
                          y={y - 26}
                          width="235"
                          height="52"
                          rx="4"
                          style={{ "--stream-color": color } as React.CSSProperties}
                        />
                        <circle cx="539" cy={y} r="12" style={{ "--stream-color": color } as React.CSSProperties} />
                        <text className="priority-number" x="539" y={y + 4} textAnchor="middle">{priority.ordinal}</text>
                        {lines.map((line, lineIndex) => (
                          <text
                            key={line}
                            className="priority-label"
                            x="560"
                            y={y + (lineIndex - (lines.length - 1) / 2) * 16 + 4}
                          >
                            {line}
                          </text>
                        ))}
                      </g>
                    );
                  })}

                  {missingOrdinals.map((ordinal) => {
                    const y = priorityY(ordinal - 1, prioritySlotCount);
                    return (
                      <g key={`missing-node-${ordinal}`} className="missing-priority-node" aria-hidden="true">
                        <rect x="520" y={y - 22} width="235" height="44" rx="4" />
                        <text x="637" y={y + 4} textAnchor="middle">{ordinal}번 항목 원문 대조 중</text>
                      </g>
                    );
                  })}

                  {selectedPriority && selectedStream && (() => {
                    const y = priorityY(selectedPriority.ordinal - 1, prioritySlotCount);
                    const color = streamColors[selectedStream.id] ?? "#6e685b";
                    return (
                      <g className="stream-node" aria-label={`장기 의제 줄기, ${selectedStream.label}`}>
                        <line x1="755" y1={y} x2="810" y2={y} style={{ stroke: color }} />
                        <circle cx="847" cy={y} r="34" style={{ "--stream-color": color } as React.CSSProperties} />
                        {splitLabel(selectedStream.label, 7, 8).map((line, index, all) => (
                          <text
                            key={line}
                            x="847"
                            y={y + (index - (all.length - 1) / 2) * 15 + 4}
                            textAnchor="middle"
                          >
                            {line}
                          </text>
                        ))}
                      </g>
                    );
                  })()}
                </svg>

                <div className="mobile-priority-list" aria-label={`${selectedYear}년 우선순위 선택`}>
                  <p>
                    <strong>{selectedYear}년</strong>
                    <span>{selectedEdition ? yearCountLabel(selectedEdition, selectedYearPriorities.length) : "항목 확인 중"}</span>
                  </p>
                  {selectedYearPriorities.map((priority) => (
                    <button
                      key={priority.id}
                      type="button"
                      className={priority.id === selectedPriority?.id ? "is-active" : ""}
                      aria-pressed={priority.id === selectedPriority?.id}
                      onClick={() => choosePriority(priority.id)}
                    >
                      <b>{priority.ordinal}</b>
                      <span>{priority.title}</span>
                    </button>
                  ))}
                  {missingOrdinals.map((ordinal) => (
                    <div key={`mobile-missing-${ordinal}`} className="is-missing">
                      <b>{ordinal}</b>
                      <span>항목 원문 대조 중</span>
                    </div>
                  ))}
                </div>

                <div className="graph-legend" aria-label="그래프 범례">
                  <span><i className="legend-government" />정부</span>
                  <span><i className="legend-year" />대상연도</span>
                  <span><i className="legend-priority" />우선순위 항목</span>
                  <span><i className="legend-stream" />장기 의제 줄기</span>
                </div>
              </div>

              <aside className="evidence-panel" id="evidence" aria-live="polite">
                <p className="section-number">02 / 선택 항목의 원문</p>
                {!archive ? (
                  <div className="panel-loading">외교백서 자료를 불러오고 있습니다.</div>
                ) : selectedPriority ? (
                  <>
                    <div className="evidence-meta">
                      <span>{selectedYear} 대상연도</span>
                      <span>{selectedPriority.ordinal}번</span>
                    </div>
                    <h3>{selectedPriority.title}</h3>
                    {selectedStream && (
                      <p className="stream-label" style={{ borderColor: streamColors[selectedStream.id] ?? "#6e685b" }}>
                        {selectedStream.label}
                      </p>
                    )}
                    <blockquote>{selectedPriority.quote}</blockquote>
                    <dl>
                      <div>
                        <dt>발간분</dt>
                        <dd>{selectedPriority.source.edition}</dd>
                      </div>
                      <div>
                        <dt>위치</dt>
                        <dd>
                          {selectedPriority.source.chapter ? `제${selectedPriority.source.chapter}장` : "장 확인 중"}
                          {" · "}
                          {selectedPriority.source.section ? `제${selectedPriority.source.section}절` : "절 확인 중"}
                          {" · "}
                          {selectedPriority.source.page ? `${selectedPriority.source.page}쪽` : "쪽수 확인 중"}
                        </dd>
                      </div>
                      <div>
                        <dt>번호 형식</dt>
                        <dd>{markStyleLabel(selectedEdition?.markStyle)}</dd>
                      </div>
                      <div>
                        <dt>배열 근거</dt>
                        <dd>{selectedPriority.ordinalSource || "확인 중"}</dd>
                      </div>
                      <div>
                        <dt>자료 상태</dt>
                        <dd>{statusLabel(selectedEdition?.status ?? "pending")}</dd>
                      </div>
                    </dl>
                    {selectedPriority.flags.length > 0 && (
                      <div className="flag-list" aria-label="자료 주의사항">
                        {selectedPriority.flags.map((flag) => <span key={flag}>{flagLabel(flag)}</span>)}
                      </div>
                    )}
                    {selectedEdition?.status === "partial" && selectedEdition.note && (
                      <p className="extraction-note"><strong>검수 메모</strong>{selectedEdition.note}</p>
                    )}
                    <button className="copy-button" type="button" onClick={copyCitation}>
                      {copied ? "인용 정보 복사됨" : "인용 정보 복사"}
                    </button>
                  </>
                ) : (
                  <div className="empty-evidence">
                    <p className="empty-year">{selectedYear}</p>
                    <h3>항목 데이터를 확인하고 있습니다.</h3>
                    <p>{selectedEdition?.note ?? "원문 대조가 끝나면 이 자리에 항목과 출처가 나타납니다."}</p>
                    <dl>
                      <div><dt>발간분</dt><dd>{selectedEdition?.title}</dd></div>
                      <div><dt>자료 상태</dt><dd>{statusLabel(selectedEdition?.status ?? "pending")}</dd></div>
                    </dl>
                  </div>
                )}
                <p className="evidence-rule">
                  이 화면은 백서가 항목을 배열한 방식을 보여줍니다. 연결선은 정책의 인과나 성과를 주장하지 않습니다.
                </p>
              </aside>
            </div>
          )}
        </section>

        <section className="reading-guide" aria-labelledby="guide-title">
          <p className="section-number">03 / 읽는 법</p>
          <div className="guide-grid">
            <h2 id="guide-title">그래프보다<br />근거가 먼저입니다.</h2>
            <div>
              <p><strong>연도는 대상연도입니다.</strong> 2003년 노드는 「2004 외교백서」가 다룬 2003년 외교활동을 뜻합니다.</p>
              <p><strong>정당색을 사용하지 않습니다.</strong> 색은 장기 의제 줄기를 구분하는 데만 쓰입니다.</p>
              <p><strong>비어 있는 가지는 숨기지 않습니다.</strong> 미입력과 원본 결손은 실제 정책의 부재와 구별해 표시합니다.</p>
            </div>
          </div>
        </section>

        <details className="text-tree">
          <summary>그래프를 텍스트 목록으로 보기</summary>
          <div className="tree-body">
            <h2>노무현 정부</h2>
            {editions.map((edition) => {
              const items = archive?.priorities
                .filter((priority) => priority.coverageYear === edition.coverageYear)
                .sort((a, b) => a.ordinal - b.ordinal) ?? [];
              return (
                <section key={edition.coverageYear}>
                  <button type="button" onClick={() => chooseYear(edition.coverageYear)}>
                    {edition.coverageYear}년 · {edition.title}
                  </button>
                  {items.length ? (
                    <ol>
                      {items.map((item) => (
                        <li key={item.id}>
                          <button type="button" onClick={() => {
                            chooseYear(edition.coverageYear);
                            choosePriority(item.id);
                          }}>
                            {item.title}
                          </button>
                        </li>
                      ))}
                    </ol>
                  ) : <p>항목 데이터 확인 중</p>}
                </section>
              );
            })}
          </div>
        </details>
      </main>
      </div>

      <SiteFooter />
    </div>
  );
}
