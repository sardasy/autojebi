import WorkspaceClient from "@/components/WorkspaceClient";

export default async function Page({params}: {params: Promise<{noticeNo: string}>}) {
  const {noticeNo} = await params;
  return <WorkspaceClient noticeNo={decodeURIComponent(noticeNo)}/>;
}
