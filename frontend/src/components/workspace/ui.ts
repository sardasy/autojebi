import { WorkspaceActor } from "@/lib/workspace";

/** Shared class names and labels for the v2 workspace screen (split out of WorkspaceClient, R6). */
export const inputClass = "block border border-gray-300 rounded p-2 w-full min-w-0 bg-white text-sm";
export const buttonClass = "inline-flex shrink-0 whitespace-nowrap items-center justify-center gap-2 border rounded px-3 py-2 text-sm disabled:opacity-40";

export const tabs = ["2. 공고 서류 검토", "3. 비교·작성", "4. 서류 확인"] as const;
export type Tab = typeof tabs[number];
/** URL hash per tab, same order as `tabs`. */
export const stepIds = ["documents", "writing", "review"];

const fieldLabels: Record<string, string> = {business_number: "사업자번호", ceo_name: "대표자명", address: "주소", org_name: "공고 기관", company_name: "회사명"};
export const readableError = (message: string) => message.replace(/\b(business_number|ceo_name|address|org_name|company_name)\b/g, key => fieldLabels[key]);
export const actorLabel = (actor?: WorkspaceActor | null) => actor ? `${actor.name} · ${{viewer: "조회자", writer: "작성자", reviewer: "검토자", approver: "최종 승인자"}[actor.role]}` : "개인 식별 정보 없음";
export const date = (value: string) => new Date(value).toLocaleString("ko-KR");

export type Mutate = (path: string, body: unknown, message?: string) => Promise<void>;
