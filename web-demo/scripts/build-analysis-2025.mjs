import { access, readFile, stat, writeFile } from "node:fs/promises";
import { constants } from "node:fs";
import { resolve } from "node:path";

const COVERAGE_YEAR = 2025;

const ACTOR_DEFINITIONS = [
  { id: "north-korea", label: "북한", pattern: "(?:북한|남북|대북|북핵)", note: "북한·남북·대북·북핵" },
  { id: "united-states", label: "미국", pattern: "(?:미국|한미|미측)", note: "미국·한미·미측" },
  { id: "china", label: "중국", pattern: "(?:중국|한중|미중)", note: "중국·한중·미중" },
  { id: "japan", label: "일본", pattern: "(?:일본|한일|미일)", note: "일본·한일·미일" },
  { id: "russia", label: "러시아", pattern: "(?:러시아|한러|러북)", note: "러시아·한러·러북" },
  { id: "asean", label: "아세안", pattern: "(?:아세안|ASEAN)", note: "아세안·ASEAN" },
  { id: "un", label: "유엔", pattern: "(?:유엔|(?<![A-Z])UN(?![A-Z]))", note: "유엔·UN" },
  { id: "g7", label: "G7", pattern: "G7", note: "G7" },
  { id: "g20", label: "G20", pattern: "G20", note: "G20" },
  { id: "apec", label: "APEC", pattern: "APEC", note: "APEC" },
  { id: "global-south", label: "글로벌 사우스", pattern: "글로벌 사우스", note: "글로벌 사우스" },
  { id: "eu", label: "EU", pattern: "(?:유럽연합|EU)(?![A-Z])", note: "유럽연합·EU" },
];

const CONCEPTS = [
  "협력",
  "안보",
  "경제",
  "국제사회",
  "국익",
  "평화",
  "공급망",
  "국민",
  "정상회의",
  "AI",
  "위기",
  "기술",
  "다자",
  "실용",
];

function normalizeText(value) {
  return value
    .normalize("NFKC")
    .replace(/[･·ㆍ‧•・]/g, "")
    .replace(/[ \t]+/g, " ")
    .replace(/\r/g, "");
}

function removeRunningHeaders(value) {
  return value
    .replace(/^\s*제\d+장_[^\n]*$/gm, " ")
    .replace(/^\s*제\d+절\s+[^\n]*$/gm, " ");
}

function countMatches(value, pattern) {
  return value.match(new RegExp(pattern, "giu"))?.length ?? 0;
}

function countCharacters(value) {
  return value.replace(/\s/g, "").length;
}

function countWords(value) {
  return value.trim().split(/\s+/).filter(Boolean).length;
}

function extractPdfPageCount(buffer) {
  const source = buffer.toString("latin1");
  const counts = [...source.matchAll(/\/Count\s+(\d+)[^<>]{0,160}?\/Type\s*\/Pages/g)]
    .map((match) => Number(match[1]))
    .filter(Number.isFinite);
  return counts.length ? Math.max(...counts) : null;
}

function extractPolicySection(documentText) {
  const start = documentText.indexOf("국민주권정부는 2025년");
  const end = documentText.indexOf("제2장_한반도", start);
  if (start < 0 || end < 0 || end <= start) {
    throw new Error("2025년 외교정책 기조 절의 경계를 찾지 못했습니다.");
  }
  return removeRunningHeaders(documentText.slice(start, end));
}

function subsectionBody(policySection, priority, nextPriority) {
  const heading = `${priority.ordinal}. ${priority.title}`;
  const start = policySection.indexOf(heading);
  if (start < 0) return null;

  const bodyStart = start + heading.length;
  const nextHeading = nextPriority ? `${nextPriority.ordinal}. ${nextPriority.title}` : null;
  const end = nextHeading ? policySection.indexOf(nextHeading, bodyStart) : policySection.length;
  if (end < bodyStart) return null;
  return policySection.slice(bodyStart, end);
}

export async function buildAnalysis2025() {
  const projectRoot = resolve(process.cwd(), "..");
  const archivePath = resolve(projectRoot, "data.json");
  const textPath = resolve(projectRoot, "text", "2025.txt");
  const pdfPath = resolve(projectRoot, "data", "2025", "2025년도 국제정세와 외교활동.pdf");
  const destination = resolve(process.cwd(), "public", "analysis-2025.json");

  const [archiveSource, extractedSource, pdfBuffer, pdfStats] = await Promise.all([
    readFile(archivePath, "utf8"),
    readFile(textPath, "utf8"),
    readFile(pdfPath),
    stat(pdfPath),
  ]);

  const archive = JSON.parse(archiveSource);
  const edition = archive.editions.find((item) => item.coverageYear === COVERAGE_YEAR);
  const streamLabels = new Map(archive.streams.map((stream) => [stream.id, stream.label]));
  const sourcePriorities = archive.priorities
    .filter((priority) => priority.coverageYear === COVERAGE_YEAR)
    .sort((left, right) => left.ordinal - right.ordinal);

  if (!edition || edition.status !== "verified") {
    throw new Error("2025년 발간분이 원문 대조 완료 상태가 아닙니다.");
  }
  if (sourcePriorities.length !== 7 || sourcePriorities.some((item, index) => item.ordinal !== index + 1)) {
    throw new Error("2025년 우선순위 1–7번의 연속성을 확인할 수 없습니다.");
  }

  const normalizedDocument = normalizeText(extractedSource);
  const cleanDocument = removeRunningHeaders(normalizedDocument);
  const policySection = extractPolicySection(normalizedDocument);
  const priorities = sourcePriorities.map((priority, index) => {
    const body = subsectionBody(policySection, priority, sourcePriorities[index + 1]);
    return {
      id: priority.id,
      ordinal: priority.ordinal,
      title: priority.title,
      streamId: priority.stream,
      streamLabel: streamLabels.get(priority.stream) ?? priority.stream,
      characters: body === null ? null : countCharacters(body),
      words: body === null ? null : countWords(body),
      quote: priority.quote,
      source: priority.source,
      flags: priority.flags,
    };
  });
  const priorityBodyWords = priorities.reduce((sum, priority) => sum + (priority.words ?? 0), 0);
  priorities.forEach((priority) => {
    priority.wordShare = priority.words === null || !priorityBodyWords
      ? null
      : Number(((priority.words / priorityBodyWords) * 100).toFixed(1));
  });
  const topThreeWords = priorities
    .filter((priority) => priority.words !== null)
    .sort((left, right) => right.words - left.words)
    .slice(0, 3)
    .reduce((sum, priority) => sum + priority.words, 0);

  const actors = ACTOR_DEFINITIONS.map((actor) => ({
    id: actor.id,
    label: actor.label,
    variants: actor.note,
    policySection: countMatches(policySection, actor.pattern),
    fullDocument: countMatches(cleanDocument, actor.pattern),
  }));

  const concepts = CONCEPTS.map((label) => ({
    label,
    count: policySection.split(label).length - 1,
  })).sort((left, right) => right.count - left.count || left.label.localeCompare(right.label, "ko"));

  const analysis = {
    meta: {
      coverageYear: COVERAGE_YEAR,
      title: edition.title,
      publishedYear: edition.publishedYear,
      administration: edition.administration,
      status: edition.status,
      sourceFile: edition.sourceFiles[0],
      sourcePath: "data/2025/2025년도 국제정세와 외교활동.pdf",
      extractionPath: "text/2025.txt",
      sourceBytes: pdfStats.size,
      sourceMegabytes: Number((pdfStats.size / 1024 / 1024).toFixed(1)),
      pageCount: extractPdfPageCount(pdfBuffer),
      chapter: edition.section.chapter,
      section: edition.section.section,
      sectionLabel: edition.section.label,
      externalDataUsed: false,
      methodVersion: "2025-single-year-v1",
    },
    summary: {
      priorityCount: priorities.length,
      priorityBodyWords,
      topThreeWordShare: priorityBodyWords
        ? Number(((topThreeWords / priorityBodyWords) * 100).toFixed(1))
        : 0,
      policySectionCharacters: countCharacters(policySection),
      documentCharacters: countCharacters(cleanDocument),
      longestPriorityId: priorities
        .filter((priority) => priority.words !== null)
        .sort((left, right) => right.words - left.words)[0]?.id ?? null,
    },
    priorities,
    actors,
    concepts,
    methodology: {
      actorUnit: "선정한 표기와 결합어의 출현 횟수",
      lengthUnit: "제목·반복 머리글을 제외한 뒤 공백으로 나눈 어절 수",
      policyScope: "제1장 제2절 외교정책 기조",
      documentScope: "2025년도 국제정세와 외교활동 전체 추출문",
      cautions: [
        "우선순위 번호는 백서에 인쇄된 순서이며 별도의 점수로 바꾸지 않았다.",
        "본문 분량과 표기 횟수는 문서 편집상의 강조를 보여주지만 정책 성과나 예산을 뜻하지 않는다.",
        "행위자 집계는 공개된 표기 사전에 따른 기계적 출현 횟수이며 문맥의 긍정·부정은 판정하지 않는다.",
      ],
    },
  };

  await writeFile(destination, `${JSON.stringify(analysis, null, 2)}\n`, "utf8");
  console.log("Built public/analysis-2025.json from the 2025 source PDF extraction");
}

export async function ensureAnalysis2025() {
  try {
    await buildAnalysis2025();
  } catch (error) {
    if (!error || typeof error !== "object" || error.code !== "ENOENT") {
      throw error;
    }
    const destination = resolve(process.cwd(), "public", "analysis-2025.json");
    await access(destination, constants.R_OK);
    console.log(`Using the packaged 2025 analysis snapshot (${error.message})`);
  }
}
