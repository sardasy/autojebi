"use client";

import {useState} from "react";
import {Workspace, workspaceApi} from "@/lib/workspace";

type Target = {version: number; output_sha256: string; unfilled_count: number; review_status: string};
const button = "rounded border px-3 py-2 text-sm disabled:opacity-40";
const checks = ["첨부 원본과 작성 위치를 확인했습니다", "작성 내용과 출처·근거를 대조했습니다", "아래 작성본을 한글에서 열어 표·쪽 나눔·서명란을 확인했습니다"];

export default function NoticeFormReview({prefix, documentId, version, busy, onSaved}: {
  prefix: string; documentId: string; version: number; busy: boolean; onSaved: (ws: Workspace) => void;
}) {
  const [target, setTarget] = useState<Target | null>(null);
  const [checked, setChecked] = useState([false, false, false]);
  const [note, setNote] = useState("");
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const path = `${prefix}/form-fillings/${encodeURIComponent(documentId)}`;
  const disabled = busy || working;
  async function start() {
    setWorking(true); setError(""); setTarget(null); setChecked([false, false, false]);
    try {
      const next = await workspaceApi<Target>(`${path}/review`);
      if (next.version !== version) throw new Error("입력이 변경되었습니다. 양식 목록을 새로고침하세요.");
      setTarget(next);
    } catch (err) {setError((err as Error).message);}
    finally {setWorking(false);}
  }
  async function review(approved: boolean) {
    if (!target || disabled || !note.trim()) return;
    setWorking(true); setError("");
    try {
      const updated = await workspaceApi<Workspace>(`${path}/review`, {
        version, output_sha256: target.output_sha256, approved, note: note.trim(),
        source_checked: checked[0], content_checked: checked[1], layout_checked: checked[2],
      });
      setTarget(null); setChecked([false, false, false]); onSaved(updated);
    } catch (err) {setError((err as Error).message); setTarget(null); setChecked([false, false, false]);}
    finally {setWorking(false);}
  }
  return <section aria-label="작성 양식 검토" className="space-y-3 rounded border p-3">
    <button className={button} disabled={disabled} onClick={() => void start()}>작성본 검토 시작</button>
    {target && <>
      <p className="text-sm">현재 검토 상태: {target.review_status === "approved" ? "승인" : target.review_status === "rejected" ? "반려" : "검토 대기"} · 미작성 {target.unfilled_count}개</p>
      <a className="block text-sm underline" href={`/api/v2${path}/download?version=${version}&output_sha256=${target.output_sha256}`}>검토할 작성본 다운로드 (HWPX)</a>
      <p className="text-xs text-gray-600">작성본의 내용과 실제 배치를 확인한 뒤 기록하세요. 양식 검토 승인은 자격증빙 승인이나 제출 준비 완료를 뜻하지 않습니다.</p>
      {checks.map((label, index) => <label key={label} className="flex items-start gap-2 text-sm"><input type="checkbox" checked={checked[index]} disabled={disabled} onChange={event => setChecked(values => values.map((value, i) => i === index ? event.target.checked : value))}/>{label}</label>)}
      <label className="block text-sm">양식 검토 의견<textarea className="block w-full rounded border p-2" value={note} disabled={disabled} maxLength={2000} onChange={event => setNote(event.target.value)}/></label>
      <div className="flex gap-2">
        <button className={button} disabled={disabled || !note.trim() || !checked.every(Boolean) || target.unfilled_count > 0} onClick={() => void review(true)}>양식 검토 승인</button>
        <button className={button} disabled={disabled || !note.trim()} onClick={() => void review(false)}>양식 검토 반려</button>
      </div>
    </>}
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
  </section>;
}
