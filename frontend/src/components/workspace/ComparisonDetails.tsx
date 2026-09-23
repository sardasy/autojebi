import {useMemo} from "react";
import {comparisonTitle, type ComparisonV2, type TextDifference, type TextChange} from "@/lib/documentComparison";
import {codepointSlicer} from "@/lib/textOffsets";

function Changes({value, items = value.changes}: {value: TextDifference; items?: TextChange[]}) {
  const before = useMemo(() => codepointSlicer(value.before_text), [value.before_text]);
  const after = useMemo(() => codepointSlicer(value.after_text), [value.after_text]);
  if (!items.length) return null;
  return <div className="space-y-2"><div className="grid md:grid-cols-2 gap-2 text-xs text-slate-600"><span>기존 본문 쪽 · 삭제 [-]</span><span>비교 기준 추출 · 추가 [+]</span></div>{items.map((change, i) => <div key={i} className="grid md:grid-cols-2 gap-2 border-b py-2 min-w-0">
    <p className="whitespace-pre-wrap break-all">{before(change.before_start-40, change.before_start)}<del className="bg-red-100 text-red-900">[- {before(change.before_start, change.before_end) || "∅"}]</del>{before(change.before_end, change.before_end+40)}</p>
    <p className="whitespace-pre-wrap break-all">{after(change.after_start-40, change.after_start)}<ins className="bg-green-100 text-green-900">[+ {after(change.after_start, change.after_end) || "∅"}]</ins>{after(change.after_end, change.after_end+40)}</p>
  </div>)}</div>;
}

export default function ComparisonDetails({value}: {value: ComparisonV2}) {
  const s = value.summary;
  return <div className="space-y-3">
    <p className="font-medium" role="status">{comparisonTitle(value)}</p>
    <p>내부 제어문 {s.control_groups}묶음 · 공백·줄바꿈 {s.whitespace}구간 · 분류 미확인 {s.unclassified}건</p>
    {value.basis === "legacy_extraction" && <p className="text-xs">기존 본문 쪽은 원본 XML에서 확인한 제어문을 제외한 기준입니다. 저장 본문은 결과 반영 전까지 유지됩니다.</p>}
    {value.completion === "truncated" && <p role="alert">전체 비교 미완료 · 비교 한도로 일부 상세를 표시하지 못했습니다. 차이 없음으로 판정하지 않습니다.</p>}
    {s.cells_not_compared && <p>기존 셀 정보 없음 · HWP는 본문만 비교합니다. 필드 명령 문자열의 차이가 있으면 제어문 여부 미확인으로 분류합니다.</p>}
    {s.cells_not_compared && s.unclassified > 0 && <p>HWP 제어문 여부 미확인 · 의심 구간은 원문과 대조하세요.</p>}
    {s.unclassified > 0 && <details open><summary>분류 미확인 · 원문 대조 필요</summary><Changes value={value} items={value.changes.filter(c => c.kind === "unclassified")}/></details>}
    <Changes value={value} items={value.changes.filter(c => c.kind === "content")}/>
    <details><summary>내부 제어문 {s.control_groups}묶음</summary><p>원본 XML로 확인한 필드 파라미터입니다. 표시 본문은 보존합니다.</p>
      {value.controls.map((control, i) => <pre key={i} className="whitespace-pre-wrap break-all border-b py-2">{control.text}</pre>)}
    </details>
    <details><summary>공백·줄바꿈 {s.whitespace}구간</summary><Changes value={value} items={value.changes.filter(c => c.kind === "whitespace")}/></details>
    {!!value.tables.length && <details open><summary>표·셀 비교</summary><p>동일 원본 XML에서 재구성한 표와 비교 기준 추출을 대조합니다. 검증된 인용이 아닙니다.</p>
      {value.tables.map((table, i) => <div key={i} className="border p-2 my-2">
        <p>표 {table.reference_table_id || "ID 없음"} · {table.status === "matched" ? `셀 변경 ${table.cells.length}개` : table.status === "structure_changed" ? "구조 변경 · 셀 비교 중단" : "대응 확인 필요"}</p>
        {table.parent_cell && <p className="break-all">상위 셀: {table.parent_cell}</p>}
        {table.cells.map(cell => <div key={`${cell.row}/${cell.col}`}><p>행 {cell.row+1} · 열 {cell.col+1}</p><Changes value={cell}/></div>)}
        {table.row_diff && <Changes value={table.row_diff}/>}
      </div>)}
    </details>}
    <p className="text-xs">비교 규칙 v2 · 실제 쪽 번호와 문서 전체의 정확성은 별도 확인이 필요합니다.</p>
  </div>;
}
