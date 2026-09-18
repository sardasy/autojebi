import { Download } from "lucide-react";
import { type SourceAttachment } from "@/lib/workspace";

function officialAttachmentUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) &&
      ["www.g2b.go.kr", "g2b.go.kr"].includes(url.hostname) &&
      !url.username && !url.password && !url.port ? url.href : null;
  } catch { return null; }
}

export default function SourceInventory({attachments, pendingIndexes = []}: {attachments: SourceAttachment[]; pendingIndexes?: number[]}) {
  const states = {missing: "파일 미확보", unread: "본문 미확인", ready: "본문 확보"};
  return <div className="min-w-0 space-y-2">
    <h2 className="text-base font-semibold">나라장터 첨부 목록</h2>
    <p className="text-sm">목록 {attachments.length}개 · 파일 연결 {attachments.filter(a => a.document_ids.length > 0).length}개 · 본문 확보 {attachments.filter(a => a.state === "ready").length}개</p>
    <table aria-label="나라장터 첨부 목록" className="w-full table-fixed text-sm">
      <thead className="text-left border-b"><tr><th scope="col" className="w-10 py-2">번호</th><th scope="col" className="py-2">파일명</th><th scope="col" className="w-28 py-2 pl-2">확보 상태</th></tr></thead>
      <tbody>{attachments.map(attachment => {
        const url = officialAttachmentUrl(attachment.url);
        return <tr key={attachment.index} className="border-b align-top">
          <td className="py-2">{attachment.index}</td>
          <td className="py-2"><div className="flex items-start gap-2 min-w-0"><span className="min-w-0 break-all">{attachment.name}</span>{url && <a href={url} target="_blank" rel="noopener noreferrer" className="shrink-0 p-1" aria-label={`${attachment.name} 나라장터 원본 열기`} title="나라장터 원본 열기"><Download size={16}/></a>}</div></td>
          <td className="py-2 pl-2">{attachment.state === "missing" && pendingIndexes.includes(attachment.index) ? "다운로드 완료 · 반영 대기" : states[attachment.state]}</td>
        </tr>;
      })}</tbody>
    </table>
  </div>;
}
