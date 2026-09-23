import {fireEvent, render, screen, waitFor, within} from "@testing-library/react";
import {beforeEach, expect, it, vi} from "vitest";
import userEvent from "@testing-library/user-event";
import CompanyAssets, {CompanyAsset} from "../CompanyAssets";
import {workspaceApi} from "@/lib/workspace";

vi.mock("@/lib/workspace",()=>({workspaceApi:vi.fn()}));
const asset:CompanyAsset={id:"asset",version:2,role:"company_evidence",validity:"expiring",details:{title:"시험 확인서",category:"business_registration",subject_business_number:"0000000000",issued_on:"2026-09-01",expires_on:"2026-09-20",active:true,no_expiry:false},file:{name:"test.pdf",sha256:"test-hash",size:123}};
const category_catalog={version:"test-v1",sha256:"test-hash",items:[
  {code:"business_registration",label:"사업자등록증",role:"company_evidence"},
  {code:"previous_proposal",label:"기존 제안서 · 참고용",role:"company_reference"},
]};
const listing={items:[asset],page:1,has_more:false,alerts:{expiring:1},category_catalog};
beforeEach(()=>vi.resetAllMocks());

it("loads on demand and links the exact asset and workspace versions without approval",async()=>{
  const reload=vi.fn().mockResolvedValue(true);
  vi.mocked(workspaceApi).mockResolvedValue(listing);
  render(<CompanyAssets noticeNo="TEST" version={4} onLinked={reload}/>);
  expect(workspaceApi).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button",{name:"중앙 회사자료 연결"}));
  await screen.findByText("30일 내 만료",{exact:true});
  fireEvent.click(screen.getByRole("button",{name:"시험 확인서 연결"}));
  await waitFor(()=>expect(reload).toHaveBeenCalledTimes(1));
  expect(workspaceApi).toHaveBeenCalledWith("/notices/TEST/company-assets/asset",{version:4,asset_version:2});
  expect(screen.getByRole("status",{name:"중앙 자료 결과"})).toHaveTextContent("미승인");
});

it("edits expiry and soft-disables with a required audit note",async()=>{
  vi.mocked(workspaceApi).mockResolvedValue(listing);
  render(<CompanyAssets/>);
  fireEvent.click(screen.getByRole("button",{name:"회사 자료 보관소"}));
  fireEvent.click(await screen.findByRole("button",{name:"시험 확인서 수정"}));
  const dialog=screen.getByRole("dialog",{name:"중앙 자료 수정"});
  fireEvent.change(within(dialog).getByLabelText("만료일"),{target:{value:"2026-10-31"}});
  fireEvent.click(within(dialog).getByLabelText("활성 자료"));
  fireEvent.change(within(dialog).getByLabelText("변경 사유"),{target:{value:"신규 증빙 확보 전 사용 중지"}});
  fireEvent.click(within(dialog).getByRole("button",{name:"저장"}));
  await waitFor(()=>expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  const call=vi.mocked(workspaceApi).mock.calls.find(([, ,method])=>method==="PUT");
  expect(call?.[0]).toBe("/company-assets/asset");
  const body=call?.[1];
  expect(body).toMatchObject({version:2,details:{active:false,expires_on:"2026-10-31"},note:"신규 증빙 확보 전 사용 중지"});
});

it("registers a file with explicit period metadata and never auto-links it",async()=>{
  vi.mocked(workspaceApi).mockResolvedValue(listing);
  render(<CompanyAssets/>);
  fireEvent.click(screen.getByRole("button",{name:"회사 자료 보관소"}));
  await waitFor(()=>expect(screen.getByRole("button",{name:"자료 등록"})).toBeEnabled());
  fireEvent.click(screen.getByRole("button",{name:"자료 등록"}));
  const dialog=screen.getByRole("dialog",{name:"중앙 자료 등록"});
  fireEvent.change(within(dialog).getByLabelText("자료명"),{target:{value:"TEST ONLY"}});
  await userEvent.upload(within(dialog).getByLabelText("원본 파일"),new File(["test"],"test.pdf",{type:"application/pdf"}));
  fireEvent.click(within(dialog).getByLabelText("원문에서 유효기간 제한 없음을 확인함"));
  expect(within(dialog).getByLabelText("자료명")).toHaveValue("TEST ONLY");
  expect((within(dialog).getByLabelText("원본 파일") as HTMLInputElement).files).toHaveLength(1);
  // jsdom's native file constraint does not reflect user-event's FileList shim.
  fireEvent.submit(dialog.querySelector("form")!);
  await waitFor(()=>expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  const call=vi.mocked(workspaceApi).mock.calls.find(([,body])=>body instanceof FormData);
  expect(call?.[0]).toBe("/company-assets");
  const form=call?.[1] as FormData;
  expect(JSON.parse(form.get("metadata") as string)).toMatchObject({title:"TEST ONLY",no_expiry:true,expires_on:null});
});

it("keeps fetch errors visible and does not expose raw server exception",async()=>{
  vi.mocked(workspaceApi).mockRejectedValue(new Error("secret exception"));
  render(<CompanyAssets/>);
  fireEvent.click(screen.getByRole("button",{name:"회사 자료 보관소"}));
  await waitFor(()=>expect(screen.getByRole("status",{name:"중앙 자료 결과"})).toHaveTextContent("불러오지 못했습니다"));
  expect(screen.queryByText("secret exception")).not.toBeInTheDocument();
});

it("uses the server category label and sends its stable code",async()=>{
  vi.mocked(workspaceApi).mockResolvedValue({...listing,category_catalog:{...category_catalog,items:[
    {code:"previous_proposal",label:"서버에서 정한 참고 분류",role:"company_reference"},
  ]}});
  render(<CompanyAssets/>);
  fireEvent.click(screen.getByRole("button",{name:"회사 자료 보관소"}));
  await waitFor(()=>expect(screen.getByRole("button",{name:"자료 등록"})).toBeEnabled());
  fireEvent.click(screen.getByRole("button",{name:"자료 등록"}));
  const dialog=screen.getByRole("dialog",{name:"중앙 자료 등록"});
  expect(within(dialog).getByRole("option",{name:"서버에서 정한 참고 분류"})).toHaveValue("previous_proposal");
  fireEvent.change(within(dialog).getByLabelText("자료명"),{target:{value:"TEST REFERENCE"}});
  fireEvent.submit(dialog.querySelector("form")!);
  await waitFor(()=>expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  const call=vi.mocked(workspaceApi).mock.calls.find(([,body])=>body instanceof FormData);
  expect(JSON.parse((call?.[1] as FormData).get("metadata") as string).category).toBe("previous_proposal");
});

it("keeps originals available but disables classification when an older server omits the catalog",async()=>{
  vi.mocked(workspaceApi).mockResolvedValue({...listing,category_catalog:undefined});
  render(<CompanyAssets/>);
  fireEvent.click(screen.getByRole("button",{name:"회사 자료 보관소"}));
  await screen.findByText(/자료 분류를 불러오지 못했습니다/);
  expect(screen.getByRole("button",{name:"자료 등록"})).toBeDisabled();
  expect(screen.getByRole("button",{name:"시험 확인서 수정"})).toBeDisabled();
  expect(screen.getByRole("link",{name:"시험 확인서 원본 다운로드"})).toHaveAttribute("href","/api/v2/company-assets/asset/download");
  expect(vi.mocked(workspaceApi).mock.calls.every(([,body])=>body===undefined)).toBe(true);
});
