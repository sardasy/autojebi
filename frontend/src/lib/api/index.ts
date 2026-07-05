// 도메인별 모듈 배럴 — 기존 `@/lib/api` 단일 파일 임포트 경로를 그대로 유지한다.
// 주의: 지시자("use client"/"use server")를 넣지 말 것 — actions.ts("use server")가 임포트함.

export * from "./client";
export * from "./types";
export * from "./notices";
export * from "./search";
export * from "./analysis";
export * from "./specItems";
export * from "./requiredDocs";
export * from "./documents";
export * from "./hwp";
export * from "./skus";
