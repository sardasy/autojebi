import type { Workspace } from "@/lib/workspace";
import { jobStates } from "@/lib/workspace";
import { buttonClass } from "./ui";
import ComparisonDetails from "./ComparisonDetails";

export default function DocumentComparison({ws, busy, run}: {
  ws: Workspace; busy: boolean; run: (kind: string) => Promise<void>;
}) {
  const history = ws.jobs.filter(job => job.kind === "document_compare");
  if (!ws.kordoc_comparison_enabled && !history.length) return null;
  const eligible = ws.inputs.documents.some(doc => doc.role === "notice_source" && /\.hwpx?$/i.test(doc.name));
  return <details className="border-y py-3">
    <summary className="cursor-pointer text-sm font-medium">문서 추출 비교 · 검증용</summary>
    <div className="space-y-3 pt-3 text-sm">
      <p>공고 HWP/HWPX의 기존 본문과 별도 추출 결과를 비교합니다. 차이는 정확도 점수가 아니며 원문·요구사항·검토 승인을 변경하지 않습니다.</p>
      <button className={buttonClass} disabled={busy || !ws.kordoc_comparison_enabled || ws.source_changed || !eligible}
        onClick={() => void run("document_compare")}>문서 추출 비교 실행</button>
      {history.map(job => <details key={job.id} open={history[0].id === job.id}>
        <summary>입력 v{job.input_version} · {jobStates[job.status] || job.status}{job.input_version !== ws.version ? " · 과거 입력 결과" : ""}</summary>
        {job.error && <p role="alert">{job.error.message}</p>}
        {(job.result?.warnings || []).map((warning, i) => <p key={i}>{warning}</p>)}
        {(job.result?.comparisons || []).map(item => <article key={item.document_id} className="my-3 border p-3 space-y-2">
          <h3 className="font-medium">{item.name}</h3>
          {item.status !== "compared" ? <p>{item.status === "failed" ? "추출 실패" : "비교 제외"} · {item.error_code}</p> : <>
            {item.comparison_v2 ? <ComparisonDetails value={item.comparison_v2}/> : <>
            <p>이전 비교 방식 · 토큰 수 기준</p>
            <p>{item.comparison?.state === "no_baseline" ? "기존 본문 없음 · 원문 대조 필요" : `기존 본문에만 있는 토큰 ${item.comparison?.missing_token_count}개 · 새 결과에만 있는 토큰 ${item.comparison?.added_token_count}개`}</p>
            <p>표 {item.candidate?.tables.length}개 · {item.candidate?.page_mode === "layout" ? "레이아웃 페이지 정보 있음" : "실제 페이지 번호 미확인"} · 원문 대조 필요</p>
            </>}
            {!!item.candidate?.warnings.length && <p>추출 경고: {item.candidate.warnings.join(", ")}</p>}
            {!!item.reference?.warnings.length && <p>추출 경고: {item.reference.warnings.join(", ")}</p>}
            <details open={!item.comparison_v2}><summary>전체 본문·추출 표 보기</summary>
            <div className="grid md:grid-cols-2 gap-3">
              <div><h4>기존 본문</h4><pre className="whitespace-pre-wrap break-words max-h-72 overflow-auto">{item.baseline_text || "기존 본문 없음"}</pre></div>
              <div><h4>비교 후보 본문</h4><pre className="whitespace-pre-wrap break-words max-h-72 overflow-auto">{item.reference?.text || item.candidate?.text || "추출 본문 없음"}</pre></div>
            </div>
            {item.reference?.tables.map((table, i) => <details key={i}><summary>추출 표 {i+1} · {table.rows}행 × {table.cols}열</summary>
              {table.cells.slice(0, 200).map((cell, j) => <p key={j} className="whitespace-pre-wrap break-all">행 {cell.row+1} / 열 {cell.col+1}: {cell.text}</p>)}
              {table.cells.length > 200 && <p>셀 200개까지만 표시합니다.</p>}
            </details>)}
            {item.candidate && <>
            <details><summary>표·셀 위치 후보 확인</summary>
              <p>블록 경로는 추출기 내부 위치입니다. 검증된 인용이나 실제 쪽 번호로 사용하지 않습니다. 최대 200개 셀을 표시합니다.</p>
              <div className="max-h-72 overflow-auto"><table className="w-full text-left"><thead><tr><th>행/열</th><th>병합</th><th>내용·위치</th></tr></thead><tbody>
                {item.candidate?.fragments.filter(f => f.kind === "table_cell").slice(0, 200).map(cell => <tr key={cell.locator}>
                  <td>{(cell.row ?? 0) + 1}/{(cell.col ?? 0) + 1}</td><td>{cell.row_span}×{cell.col_span}</td>
                  <td className="whitespace-pre-wrap break-all">{cell.text}<small className="block">{cell.locator}</small></td>
                </tr>)}
              </tbody></table></div>
            </details>
            </>}
            </details>
            <details><summary>출처 해시·추출기</summary><p className="break-all">SHA-256: {item.source_sha256} · kordoc {job.result?.engine_version}</p></details>
          </>}
        </article>)}
      </details>)}
    </div>
  </details>;
}
