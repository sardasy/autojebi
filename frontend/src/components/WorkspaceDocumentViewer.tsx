"use client";

import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Download } from "lucide-react";
import { SourceDocument } from "@/lib/workspace";

export default function WorkspaceDocumentViewer({documents, prefix}: {documents: SourceDocument[]; prefix: string}) {
  const [selected, setSelected] = useState(documents[0]?.id || "");
  const [mode, setMode] = useState("text");
  const [page, setPage] = useState(1);
  const [count, setCount] = useState(1);
  const [image, setImage] = useState("");
  const [error, setError] = useState("");
  const document = documents.find(d => d.id === selected) || documents[0];
  useEffect(() => {
    if (mode !== "pdf" || !document) return;
    const controller = new AbortController();
    let objectUrl = "";
    setImage(""); setError("");
    void fetch(`/api/v2${prefix}/documents/${encodeURIComponent(document.id)}/preview?page=${page}`, {signal: controller.signal}).then(async response => {
      if (!response.ok) throw new Error("PDF 미리보기 실패 · 추출 본문 또는 원본 다운로드로 확인하세요.");
      const blob = await response.blob();
      if (controller.signal.aborted) return;
      objectUrl = URL.createObjectURL(blob);
      setCount(Number(response.headers.get("x-page-count")) || 1); setImage(objectUrl);
    }).catch(e => {if (!controller.signal.aborted) setError((e as Error).message);});
    return () => {controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl);};
  }, [document?.id, mode, page, prefix]);
  if (!document) return <p className="text-sm text-gray-500">공고 원문을 등록하면 여기에서 확인할 수 있습니다.</p>;
  const url = `/api/v2${prefix}/documents/${encodeURIComponent(document.id)}/download`;
  return <section className="min-w-0 space-y-3" aria-label="공고 원문 미리보기">
    <div className="flex gap-2"><select aria-label="미리볼 원문" className="w-full min-w-0 rounded border p-2 text-sm" value={document.id} onChange={e => {setSelected(e.target.value); setMode("text"); setPage(1);}}>{documents.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select><a href={url} aria-label="선택 원문 다운로드" title="원문 다운로드" className="border p-2 rounded"><Download size={18}/></a></div>
    <div role="group" aria-label="원문 보기 방식" className="flex gap-2 text-sm"><button type="button" aria-pressed={mode === "text"} onClick={() => setMode("text")} className={`px-3 py-2 border-b-2 ${mode === "text" ? "border-red-700" : "border-transparent"}`}>추출 본문</button>{document.name.toLowerCase().endsWith(".pdf") && <button type="button" aria-pressed={mode === "pdf"} onClick={() => setMode("pdf")} className={`px-3 py-2 border-b-2 ${mode === "pdf" ? "border-red-700" : "border-transparent"}`}>PDF 원본</button>}</div>
    {mode === "pdf" ? <><div className="flex items-center gap-3 text-sm"><button aria-label="이전 페이지" title="이전 페이지" disabled={page <= 1} onClick={() => setPage(page - 1)} className="p-2 border rounded disabled:opacity-40"><ChevronLeft size={16}/></button><span>{page} / {count}</span><button aria-label="다음 페이지" title="다음 페이지" disabled={page >= count} onClick={() => setPage(page + 1)} className="p-2 border rounded disabled:opacity-40"><ChevronRight size={16}/></button></div><div className="h-[520px] overflow-auto border bg-white">{image ? <img src={image} alt={`${document.name} ${page}페이지 원본`} className="w-full h-auto"/> : <p role="status" className="p-4 text-sm">{error || "원문 페이지 불러오는 중"}</p>}</div></> : <div className="h-[520px] overflow-auto border bg-white p-4 whitespace-pre-wrap break-words text-sm leading-7">{document.text || "본문 미확인 · 본문 추출 또는 변환본 등록 필요"}</div>}
  </section>;
}
