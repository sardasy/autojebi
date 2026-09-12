import {fireEvent, render, screen, waitFor} from "@testing-library/react";
import {beforeEach, describe, expect, it, vi} from "vitest";
import DocumentWritingWorkspace, {searchUrl} from "../DocumentWritingWorkspace";
import {Workspace, workspaceApi} from "@/lib/workspace";

vi.mock("@/lib/workspace",()=>({workspaceApi:vi.fn()}));
const makeWorkspace = (): Workspace => ({notice_no:"WRITING",version:1,decision:"pending",ready:false,source_changed:false,writing_plan_current:true,
  inputs:{writing_plan:{reviewed_at:"2026-09-11",reviewed_version:1,items:[{id:"proposal",title:"정성제안서",document_kind:"qualitative_proposal",action:"write",document_id:"source",quote:"정성제안서"},{id:"bid",title:"입찰서",document_kind:"bid_document",action:"write",document_id:"source",quote:"입찰서"}]},notice:{title:"Sample",org_name:null,close_date:null,base_price:null},documents:[{id:"ref",name:"회사 제안서",role:"company_reference",confirmed:false,text:"기존 기술 자료",text_origin:"manual"}],requirements:[],checklist:[],company:{},source_reviewed:false,legacy_warning:false,proposal_sections:[]},jobs:[],reviews:[],blockers:[],next_action:""});
describe("document writing",()=>{
  beforeEach(()=>vi.clearAllMocks());
  it("does not invent generic documents before source review",()=>{
    const ws=makeWorkspace();ws.writing_plan_current=false;delete ws.inputs.writing_plan;
    render(<DocumentWritingWorkspace ws={ws} prefix="/notices/WRITING" busy={false} onSaved={vi.fn()} onRefresh={vi.fn()}/>);
    expect(screen.queryByLabelText("서류 작성 내용")).not.toBeInTheDocument();
    expect(screen.getByRole("button",{name:"공고 서류 검토로 이동"})).toBeInTheDocument();
  });
  it("preserves separate unsaved bodies when switching documents",()=>{
    render(<DocumentWritingWorkspace ws={makeWorkspace()} prefix="/notices/WRITING" busy={false} onSaved={vi.fn()} onRefresh={vi.fn()}/>);
    fireEvent.change(screen.getByLabelText("서류 작성 내용"),{target:{value:"제안서 내용"}});
    fireEvent.click(screen.getByRole("button",{name:"입찰서 미작성"}));
    fireEvent.change(screen.getByLabelText("서류 작성 내용"),{target:{value:"입찰서 내용"}});
    fireEvent.click(screen.getByRole("button",{name:"정성제안서 저장 전"}));
    expect(screen.getByLabelText("서류 작성 내용")).toHaveValue("제안서 내용");
  });
  it("retains editor text on save failure and never turns a reference into evidence",async()=>{
    vi.mocked(workspaceApi).mockRejectedValue(new Error("다른 변경사항이 있습니다."));
    render(<DocumentWritingWorkspace ws={makeWorkspace()} prefix="/notices/WRITING" busy={false} onSaved={vi.fn()} onRefresh={vi.fn()}/>);
    fireEvent.change(screen.getByLabelText("참고할 회사 자료"),{target:{value:"ref"}});
    fireEvent.change(screen.getByLabelText("참고 발췌문"),{target:{value:"기존 기술 자료"}});
    fireEvent.click(screen.getByRole("button",{name:"발췌문 넣기"}));
    fireEvent.click(screen.getByRole("button",{name:"서류 초안 저장"}));
    await waitFor(()=>expect(screen.getByRole("status")).toHaveTextContent("다른 변경사항"));
    expect(screen.getByLabelText("서류 작성 내용")).toHaveValue("[검증필요] 기존 기술 자료");
    const body = vi.mocked(workspaceApi).mock.calls[0][1] as Record<string,unknown>;
    expect(body.references).toEqual([{document_id:"ref",quote:"기존 기술 자료"}]);
    expect(body).not.toHaveProperty("evidence_ids");
  });
  it("encodes search queries and rejects unsafe saved web links",()=>{
    expect(searchUrl("HILS & 시험", "google")).toBe(`https://www.google.com/search?q=${encodeURIComponent("HILS & 시험")}`);
    render(<DocumentWritingWorkspace ws={makeWorkspace()} prefix="/notices/WRITING" busy={false} onSaved={vi.fn()} onRefresh={vi.fn()}/>);
    fireEvent.click(screen.getByRole("button",{name:"웹검색"}));
    fireEvent.change(screen.getByLabelText("웹 자료 제목"),{target:{value:"자료"}});
    fireEvent.change(screen.getByLabelText("출처 URL"),{target:{value:"javascript:alert(1)"}});
    fireEvent.change(screen.getByLabelText("웹 자료 발췌문"),{target:{value:"내용"}});
    fireEvent.click(screen.getByRole("button",{name:"웹 자료 넣기"}));
    expect(screen.getByRole("status")).toHaveTextContent("http(s)");
    expect(screen.getByLabelText("서류 작성 내용")).toHaveValue("");
  });

  it.each(["company_reference", "company_evidence", "product_evidence"] as const)("prefills selected %s without inserting, saving, or approving", async role=>{
    const ws=makeWorkspace();
    ws.inputs.documents=[{id:"selected",name:"선택 자료",role,confirmed:role!=="company_reference",text:"선택한 근거 인용",text_origin:"manual"}];
    const selectedEvidence={document_id:"selected",quote:"선택한 근거 인용",key:"pick-1",input_version:1};
    const onSaved=vi.fn();
    const props={ws,prefix:"/notices/WRITING",busy:false,onSaved,onRefresh:vi.fn()};
    const view=render(<DocumentWritingWorkspace {...props}/>);
    fireEvent.click(screen.getByRole("button",{name:"웹검색"}));
    view.rerender(<DocumentWritingWorkspace {...props} selectedEvidence={selectedEvidence}/>);
    expect(screen.getByRole("button",{name:"회사 자료"})).toHaveAttribute("aria-pressed","true");
    expect(screen.getByLabelText("참고할 회사 자료")).toHaveValue("selected");
    expect(screen.getByRole("textbox",{name:"참고 발췌문"})).toHaveValue("선택한 근거 인용");
    expect(screen.getByLabelText("서류 작성 내용")).toHaveValue("");
    expect(screen.getByRole("button",{name:"서류 초안 저장"})).toBeDisabled();
    expect(workspaceApi).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button",{name:"발췌문 넣기"}));
    expect(screen.getByLabelText("서류 작성 내용")).toHaveValue("[검증필요] 선택한 근거 인용");
    expect(workspaceApi).not.toHaveBeenCalled();
    view.rerender(<DocumentWritingWorkspace {...props} ws={{...ws}} selectedEvidence={{...selectedEvidence}}/>);
    expect(screen.getByRole("textbox",{name:"참고 발췌문"})).toHaveValue("");
    const saved:Workspace={...ws,version:2,inputs:{...ws.inputs,proposal_sections:[{
      id:"proposal",title:"정성제안서",document_kind:"qualitative_proposal",text:"[검증필요] 선택한 근거 인용",
      references:[{document_id:"selected",quote:"선택한 근거 인용"}],review_status:"pending",evidence_ids:[],
    }]}};
    vi.mocked(workspaceApi).mockResolvedValueOnce(saved);
    fireEvent.click(screen.getByRole("button",{name:"서류 초안 저장"}));
    await waitFor(()=>expect(onSaved).toHaveBeenCalledWith(saved));
    expect(workspaceApi).toHaveBeenCalledTimes(1);
    const body=vi.mocked(workspaceApi).mock.calls[0][1] as Record<string,unknown>;
    expect(body.references).toEqual([{document_id:"selected",quote:"선택한 근거 인용"}]);
    expect(body).not.toHaveProperty("approved");
    expect(body).not.toHaveProperty("evidence_ids");
    expect(ws.inputs.documents[0]).toMatchObject({role,confirmed:role!=="company_reference"});
  });

  it("keeps an existing unsaved body when a new evidence selection arrives",()=>{
    const ws=makeWorkspace();
    const props={ws,prefix:"/notices/WRITING",busy:false,onSaved:vi.fn(),onRefresh:vi.fn()};
    const view=render(<DocumentWritingWorkspace {...props}/>);
    fireEvent.change(screen.getByLabelText("서류 작성 내용"),{target:{value:"담당자가 작성 중인 내용"}});
    view.rerender(<DocumentWritingWorkspace {...props} selectedEvidence={{document_id:"ref",quote:"기존 기술 자료",input_version:1,key:"new-pick"}}/>);
    expect(screen.getByLabelText("서류 작성 내용")).toHaveValue("담당자가 작성 중인 내용");
    expect(screen.getByRole("textbox",{name:"참고 발췌문"})).toHaveValue("기존 기술 자료");
    expect(workspaceApi).not.toHaveBeenCalled();
  });

  it.each(["unconfirmed", "asset_issue", "notice_source", "missing", "stale", "quote_mismatch"])("rejects %s selections without changing the draft",reason=>{
    const ws=makeWorkspace();
    ws.inputs.documents=[{id:"doc",name:"시험 자료",role:reason==="notice_source"?"notice_source":"product_evidence",confirmed:reason!=="unconfirmed",text:"근거 원문",text_origin:"manual",...(reason==="asset_issue"?{asset_issue:"expired"}:{})}];
    render(<DocumentWritingWorkspace ws={ws} prefix="/notices/WRITING" busy={false} onSaved={vi.fn()} onRefresh={vi.fn()} selectedEvidence={{
      document_id:reason==="missing"?"absent":"doc",quote:reason==="quote_mismatch"?"없는 인용":"근거 원문",key:"invalid",input_version:reason==="stale"?0:1,
    }}/>);
    expect(screen.getByRole("status")).toHaveTextContent("작성 내용은 변경하지 않았습니다");
    expect(screen.getByLabelText("서류 작성 내용")).toHaveValue("");
    expect(screen.queryByRole("button",{name:"발췌문 넣기"})).not.toBeInTheDocument();
    if (["unconfirmed","asset_issue","notice_source"].includes(reason)) expect(screen.queryByRole("option",{name:"시험 자료"})).not.toBeInTheDocument();
    expect(workspaceApi).not.toHaveBeenCalled();
  });

  it("requires a fresh selection after the input version changes",()=>{
    const ws=makeWorkspace();
    const picked={document_id:"ref",quote:"기존 기술 자료",key:"pick-1",input_version:1};
    const props={ws,prefix:"/notices/WRITING",busy:false,onSaved:vi.fn(),onRefresh:vi.fn(),selectedEvidence:picked};
    const view=render(<DocumentWritingWorkspace {...props}/>);
    view.rerender(<DocumentWritingWorkspace {...props} ws={{...ws,version:2}}/>);
    expect(screen.getByRole("button",{name:"발췌문 넣기"})).toBeDisabled();
    expect(screen.getByLabelText("서류 작성 내용")).toHaveValue("");
    view.rerender(<DocumentWritingWorkspace {...props} ws={{...ws,version:2}} selectedEvidence={{...picked,key:"pick-2",input_version:2}}/>);
    expect(screen.getByRole("button",{name:"발췌문 넣기"})).toBeEnabled();
    expect(workspaceApi).not.toHaveBeenCalled();
  });
});
