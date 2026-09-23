"use client";

import {useState} from "react";
import {Workspace, workspaceApi} from "@/lib/workspace";
import {hasAttachmentOnlyPlan} from "./workspace/outputPlan";

const button = "rounded border px-3 py-2 text-sm disabled:opacity-40";

export default function WorkspaceOutputPlan({ws, prefix, templates, busy, onSaved}: {
  ws: Workspace; prefix: string; templates: {template_key: string; name: string}[];
  busy: boolean; onSaved: (updated: Workspace) => void;
}) {
  const [selected, setSelected] = useState(ws.inputs.output_plan?.template_keys || ["bid_form", "proposal"]);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const disabled = busy || saving || ws.source_changed;
  const canOmitHwp = hasAttachmentOnlyPlan(ws);
  const unknown = selected.filter(key => !templates.some(template => template.template_key === key));
  const validSelection = selected.length ? !unknown.length : canOmitHwp;
  async function save() {
    if (disabled || !validSelection || !note.trim()) return;
    setSaving(true); setError("");
    try {
      onSaved(await workspaceApi<Workspace>(`${prefix}/output-plan`, {
        version: ws.version, template_keys: selected, note: note.trim(),
      }, "PUT"));
    } catch (err) {setError((err as Error).message);}
    finally {setSaving(false);}
  }
  return <details className="border-y py-3" open={!ws.inputs.output_plan}>
    <summary className="cursor-pointer text-sm font-medium">최종 패키지에 필요한 서류</summary>
    <form className="mt-3 space-y-3" aria-label="출력 서류 계획" onSubmit={event => {event.preventDefault(); void save();}}>
      <p className="text-sm text-gray-600">공고에서 요구한 HWP 서류를 선택하세요. Excel, 공고 원본, 작성한 원본 양식은 함께 포함됩니다. 계획을 바꾸면 새 입력 버전에서 생성·파일 검토를 다시 진행합니다.</p>
      {canOmitHwp && <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={!selected.length} disabled={disabled} onChange={event => setSelected(event.target.checked ? [] : ["bid_form", "proposal"])}/>HWP 생성 불필요 · 확인한 작성 대상은 원본 첨부·전자 제출만 있습니다.</label>}
      <fieldset disabled={disabled || !templates.length} className="space-y-2">
        <legend className="text-sm font-medium mb-2">필요한 HWP 서류</legend>
        {templates.map(template => <label key={template.template_key} className="flex items-start gap-2 text-sm">
          <input type="checkbox" checked={selected.includes(template.template_key)} onChange={event => setSelected(current => event.target.checked ? [...current, template.template_key] : current.filter(key => key !== template.template_key))}/>
          {template.name}
        </label>)}
        {unknown.map(key => <label key={key} className="flex items-start gap-2 text-sm">
          <input type="checkbox" checked onChange={() => setSelected(current => current.filter(value => value !== key))}/>
          목록에 없는 양식: {key}
        </label>)}
      </fieldset>
      {!!unknown.length && <p role="status" className="text-sm text-amber-800">현재 목록에 없는 양식이 선택되어 있습니다. 템플릿 목록을 확인하세요.</p>}
      {!selected.length && <p role="status" className={`text-sm ${canOmitHwp ? "text-gray-600" : "text-amber-800"}`}>{canOmitHwp ? "Excel과 필요한 원본·양식의 검토는 계속 진행합니다. 전자 제출은 담당자가 직접 수행합니다." : "직접 작성할 항목이 없음을 공고 서류 검토에서 확인하거나 HWP 서류를 하나 이상 선택하세요."}</p>}
      <label className="block text-sm">출력 서류 확인 의견<textarea className="mt-1 block w-full rounded border p-2" value={note} maxLength={2000} disabled={disabled} onChange={event => setNote(event.target.value)}/></label>
      <button className={button} disabled={disabled || !validSelection || !note.trim()}>출력 서류 계획 저장</button>
      {ws.inputs.output_plan?.note && <p className="text-sm text-gray-600">저장된 확인 의견: {ws.inputs.output_plan.note}</p>}
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    </form>
  </details>;
}
