"use client";

import {useEffect, useState} from "react";
import {type Workspace, workspaceApi} from "@/lib/workspace";

export default function SourceDisplayReview({ws, prefix, onSaved}: {ws: Workspace; prefix: string; onSaved: (ws: Workspace) => void}) {
  const [kind, setKind] = useState("absent"), [label, setLabel] = useState("");
  const [first, setFirst] = useState(""), [second, setSecond] = useState("");
  const [note, setNote] = useState(""), [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  const docs = ws.inputs.documents.filter(d => d.role === "notice_source");
  const brief = ws.notice_brief;
  useEffect(() => {setChecked(false);}, [brief?.source_signature, kind, label, first, second]);
  if (!brief?.version) return null;
  const labels = [brief.submission_state, ...brief.points].filter(p => !p.items.length);
  const input = "block w-full border rounded p-2 text-sm";
  return <details className="border-y py-3"><summary>원본 대조 기록 · 항목 부재 / 동일 문서 확인</summary>
    <form className="space-y-3 pt-3" onSubmit={async e => {
      e.preventDefault(); setBusy(true); setMessage("");
      try {
        const result = await workspaceApi<Workspace>(`${prefix}/source-display-reviews`, {
          version: ws.version, kind, label: kind === "absent" ? label : "",
          document_ids: kind === "absent" ? docs.map(d => d.id) : [first, second],
          source_signature: brief.source_signature, original_checked: checked, note,
        }); onSaved(result); setChecked(false); setNote(""); setMessage("원본 대조 기록 저장 완료");
      } catch (error) {setMessage((error as Error).message);} finally {setBusy(false);}
    }}>
      <label>확인 종류<select className={input} value={kind} onChange={e => {setKind(e.target.value); setChecked(false);}}><option value="absent">원문에 항목 없음 확인</option><option value="equivalent">서로 다른 형식의 동일 문서 확인</option></select></label>
      {kind === "absent" ? <><label>확인 항목<select required className={input} value={label} onChange={e => setLabel(e.target.value)}><option value="">선택</option>{labels.map(p => <option key={p.label}>{p.label}</option>)}</select></label><p>확인 범위: 전체 공고 원본</p><ul>{docs.map(d => <li key={d.id}><a className="underline" href={`/api/v2${prefix}/documents/${encodeURIComponent(d.id)}/download`}>{d.name}</a></li>)}</ul></> : <>
        <p>파일명 일치만으로 동일 문서가 되지 않습니다. 두 원본의 전체 내용을 대조하세요.</p>
        <label>첫 번째 원본<select required className={input} value={first} onChange={e => {setFirst(e.target.value); setChecked(false);}}><option value="">선택</option>{docs.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
        <label>두 번째 원본<select required className={input} value={second} onChange={e => {setSecond(e.target.value); setChecked(false);}}><option value="">선택</option>{docs.filter(d => d.id !== first).map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
      </>}
      <label>확인 의견<textarea required className={input} value={note} onChange={e => setNote(e.target.value)}/></label>
      <label className="block"><input type="checkbox" required checked={checked} onChange={e => setChecked(e.target.checked)}/> 지정한 범위의 실제 원본을 직접 대조했습니다.</label>
      <button className="border rounded px-3 py-2" disabled={busy || ws.source_changed || !checked || !note.trim()}>원본 대조 기록 저장</button><p role="status">{message}</p>
    </form>
  </details>;
}
