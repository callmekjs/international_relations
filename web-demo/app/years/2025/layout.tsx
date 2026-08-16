import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "2025 외교백서 데이터 분석 — 외교의 순서",
  description: "2025년도 국제정세와 외교활동 원문만으로 정책 배열, 본문 분량, 행위자와 핵심어 출현을 분석합니다.",
};

export default function Year2025Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
