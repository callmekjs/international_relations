import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "외교의 순서 — 1989–2025 외교백서 아카이브",
  description: "대한민국 외교백서의 연도별 정책 배열을 시간축, 정부별 그래프, 정권 이음매와 원문 근거로 탐색하는 데이터 아카이브",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
