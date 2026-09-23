import type {Workspace} from "@/lib/workspace";

/** Display server reasons without deriving a second readiness decision. */
export default function WorkspaceReadiness({ws}: {ws: Workspace}) {
  if (!ws.readiness_issues) {
    return <ul aria-label="제출 준비 확인 사항" className="text-sm text-amber-800 list-disc pl-5">
      {ws.blockers.map((message, index) => <li key={index}>{message}</li>)}
    </ul>;
  }
  return <section aria-label="제출 준비 확인 사항" className="text-sm space-y-2">
    {ws.readiness_checked_at && <p className="text-gray-500">확인 시각: {new Date(ws.readiness_checked_at).toLocaleString("ko-KR")} · 입력 버전 {ws.version}</p>}
    <ul className="space-y-2">
      {ws.readiness_issues.map((reason, index) => <li key={`${reason.code}-${reason.entity_id}-${index}`} className="border-l-2 border-amber-400 pl-3">
        <p className="text-amber-800">{reason.message}</p>
        <p className="text-gray-600">{reason.next_action}</p>
      </li>)}
    </ul>
  </section>;
}
