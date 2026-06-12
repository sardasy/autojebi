import type { Lifecycle, SortDirection, SortField } from "@/lib/api";

export const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: "collected", label: "수집" },
  { value: "analyzed", label: "분석" },
  { value: "form_filled", label: "양식" },
  { value: "notified", label: "알림" },
  { value: "digest_queued", label: "다이제스트" },
  { value: "archived_low", label: "보류" },
];

export const CATEGORY_OPTIONS: { value: string; label: string }[] = [
  { value: "HIL", label: "HIL" },
  { value: "SW", label: "SW" },
  { value: "IGBT", label: "IGBT" },
  { value: "SCR", label: "SCR" },
  { value: "수동소자", label: "수동소자" },
  { value: "ABB장비", label: "ABB장비" },
  { value: "혼합", label: "혼합" },
  { value: "비분류", label: "비분류" },
];

export const BID_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: "용역", label: "용역" },
  { value: "물품", label: "물품" },
  { value: "공사", label: "공사" },
  { value: "외자", label: "외자" },
  { value: "goods", label: "물품(goods)" },
  { value: "service", label: "용역(service)" },
  { value: "construction", label: "공사(construction)" },
  { value: "foreign", label: "외자(foreign)" },
];

export const SOURCE_OPTIONS: { value: string; label: string }[] = [
  { value: "G2B", label: "G2B" },
  { value: "KJEBI", label: "KJEBI" },
];

export const LIFECYCLE_OPTIONS: { value: Lifecycle; label: string }[] = [
  { value: "active", label: "진행 중" },
  { value: "closed", label: "마감됨" },
  { value: "unknown", label: "마감 미확인" },
  { value: "all", label: "전체" },
];

export const SORT_OPTIONS: { value: SortField; label: string }[] = [
  { value: "close_date", label: "마감일" },
  { value: "updated_at", label: "업데이트일" },
  { value: "base_price", label: "예가" },
  { value: "fit_score", label: "적합도" },
  { value: "score_total", label: "종합 점수" },
];

export const DIRECTION_OPTIONS: { value: SortDirection; label: string }[] = [
  { value: "asc", label: "오름차순" },
  { value: "desc", label: "내림차순" },
];

export const PAGE_SIZE_OPTIONS: number[] = [10, 20, 50, 100];

export const PERIOD_QUICK_OPTIONS: { value: string; label: string; days: number | null }[] = [
  { value: "all", label: "전체", days: null },
  { value: "today", label: "당일", days: 0 },
  { value: "w1", label: "1주일", days: 7 },
  { value: "m1", label: "1개월", days: 30 },
  { value: "m6", label: "6개월", days: 180 },
  { value: "y1", label: "1년", days: 365 },
];

export const DEFAULT_LIFECYCLE: Lifecycle = "active";
export const DEFAULT_SORT: SortField = "close_date";
export const DEFAULT_DIRECTION: SortDirection = "asc";
export const DEFAULT_PAGE_SIZE = 20;
