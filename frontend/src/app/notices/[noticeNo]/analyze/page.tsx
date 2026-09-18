import { redirect } from "next/navigation";
export default async function LegacyPage({ params }: { params: Promise<{ noticeNo: string }> }) {
  const { noticeNo } = await params;
  redirect(`/notices/${encodeURIComponent(decodeURIComponent(noticeNo))}?tab=documents`);
}
