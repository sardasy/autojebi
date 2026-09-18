export function deadlineState(value: string | null, now = Date.now()) {
  if (!value || !Number.isFinite(Date.parse(value))) return "마감 미확인";
  return Date.parse(value) <= now ? "마감" : "마감 전";
}
