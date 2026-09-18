"use client";

import {useState} from "react";
import {decisions, Workspace, workspaceApi} from "@/lib/workspace";

export default function WorkspaceDecision({ws, prefix, busy, onSaved}: {
  ws: Workspace; prefix: string; busy: boolean; onSaved: (updated: Workspace) => void;
}) {
  const [decision, setDecision] = useState(ws.decision);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const disabled = busy || saving || ws.source_changed;
  async function save() {
    if (disabled || !note.trim() || decision === ws.decision) return;
    setSaving(true); setError("");
    try {
      onSaved(await workspaceApi<Workspace>(`${prefix}/decision`, {version: ws.version, decision, note: note.trim()}));
    } catch (err) {setError((err as Error).message);}
    finally {setSaving(false);}
  }
  return <details className="border-y py-3" open={ws.decision === "pending"}>
    <summary className="cursor-pointer text-sm font-medium">참가 결정 · {decisions[ws.decision] || ws.decision}</summary>
    <form aria-label="참가 결정 확인" className="mt-3 space-y-3" onSubmit={event => {event.preventDefault(); void save();}}>
      <p className="text-sm text-gray-600">참가 여부를 확인한 뒤 최종 서류를 생성하세요. 결정을 바꾸면 새 입력 버전에서 생성·파일 검토를 다시 진행합니다.</p>
      <label className="block text-sm">참가 결정<select aria-label="참가 결정" className="mt-1 block rounded border p-2" value={decision} disabled={disabled} onChange={event => setDecision(event.target.value)}>
        {Object.entries(decisions).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <label className="block text-sm">참가 결정 의견<textarea className="mt-1 block w-full rounded border p-2" value={note} disabled={disabled} maxLength={2000} onChange={event => setNote(event.target.value)}/></label>
      <button className="rounded border px-3 py-2 text-sm disabled:opacity-40" disabled={disabled || !note.trim() || decision === ws.decision}>참가 결정 저장</button>
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    </form>
  </details>;
}
