import type {Workspace} from "@/lib/workspace";

/** An empty output plan is available only after the current source plan was reviewed. */
export function hasAttachmentOnlyPlan(ws: Workspace): boolean {
  const items = ws.inputs.writing_plan?.items || [];
  return !ws.source_changed && !!ws.writing_plan_current && !!items.length
    && items.every(item => ["attach", "electronic"].includes(item.action));
}
