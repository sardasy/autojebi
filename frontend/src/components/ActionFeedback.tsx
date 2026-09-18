"use client";

export function ActionFeedback({ message, detail, error = false }: { message: string; detail?: string | null; error?: boolean }) {
  if (!message) return null;
  return <div role="status" className={`my-3 border-l-4 px-3 py-2 text-sm ${error ? "border-red-600 bg-red-50 text-red-800" : "border-cyan-700 bg-cyan-50 text-slate-800"}`}>
    <p>{message}</p>
    {detail && <details className="mt-2"><summary className="cursor-pointer text-xs">기술 상세</summary><pre className="mt-2 max-h-40 overflow-auto text-xs">{detail}</pre></details>}
  </div>;
}
