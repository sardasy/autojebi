import { describe, expect, it } from "vitest";
import { deriveWorkspace, layoutReviewed, nextStep } from "../workspace/derive";
import { Workspace, WorkspaceJob } from "@/lib/workspace";

const prefix = "/notices/N";
const job = (over: Partial<WorkspaceJob>): WorkspaceJob =>
  ({id: "j", notice_no: "N", kind: "extract", status: "succeeded", input_version: 1, created_at: "2026-09-18T00:00:00Z", ...over}) as WorkspaceJob;
const source = {id: "s", name: "공고.pdf", role: "notice_source", confirmed: true, text: "본문", text_origin: "pdf"} as const;
const ws = (over: Partial<Workspace> = {}, inputs: Partial<Workspace["inputs"]> = {}): Workspace => ({
  notice_no: "N", version: 1, decision: "pending", ready: false, source_changed: false, blockers: [], next_action: "다음 작업", jobs: [], reviews: [],
  inputs: {notice: {title: "t", org_name: null, close_date: null, base_price: null}, documents: [source], requirements: [], checklist: [],
    source_reviewed: true, legacy_warning: false, company: {}, ...inputs},
  ...over,
}) as Workspace;
const step = (w: Workspace | null) => nextStep(w, prefix, deriveWorkspace(w));

describe("nextStep priority", () => {
  it("returns null without a workspace", () => expect(step(null)).toBeNull());
  it("a running job disables the action", () => {
    const running = step(ws({jobs: [job({status: "running", kind: "analyze"})]}));
    expect(running).toMatchObject({label: "처리 중", disabled: true});
    expect(running?.action).toBeUndefined();
  });
  it("source changes come before everything else", () => {
    expect(step(ws({source_changed: true}))?.action).toEqual({type: "mutate", path: `${prefix}/sync`, body: {version: 1}, message: "원문 동기화 완료"});
  });
  it("no source documents asks to fetch attachments", () => {
    expect(step(ws({}, {documents: []}))?.action).toEqual({type: "run", kind: "fetch"});
  });
  it("unread source text asks to extract", () => {
    expect(step(ws({}, {documents: [{...source, text: ""}]}))?.action).toEqual({type: "run", kind: "extract"});
  });
  it("a finished fetch with new documents asks to apply it", () => {
    const fetched = job({id: "f", kind: "fetch", result: {documents: [{id: "new", role: "notice_source"}]}} as Partial<WorkspaceJob>);
    expect(step(ws({jobs: [fetched]}))?.action).toMatchObject({type: "mutate", path: `${prefix}/jobs/f/apply`});
  });
  it("missing requirements go to the notice brief", () => {
    expect(step(ws())?.action).toEqual({type: "goto", tab: "2. 공고 서류 검토", target: "notice-brief"});
  });
  it("a missing HWP required value links to company settings", () => {
    const blocked = job({kind: "hwp", status: "failed", error: {code: "required_missing", message: "", next_action: ""}} as Partial<WorkspaceJob>);
    expect(step(ws({jobs: [blocked]}, {requirements: [{id: "r"}] as Workspace["inputs"]["requirements"]}))).toMatchObject({href: "/admin#company"});
  });
  it("ready workspace points to the final package", () => {
    const w = ws({ready: true, source_attachments: []}, {requirements: [{id: "r"}] as Workspace["inputs"]["requirements"],
      proposal_sections: [{id: "p", text: "x", review_status: "approved", evidence_ids: []}]});
    expect(step(w)?.action).toEqual({type: "goto", tab: "4. 서류 확인", target: "generated-files"});
  });
});

describe("layoutReviewed", () => {
  it("requires an approved, layout-confirmed review of the same current file", () => {
    const hwp = job({kind: "hwp", result: {sha256: "a"}} as Partial<WorkspaceJob>);
    const review = {id: "r", job_id: "j", action: "approved", note: "", input_version: 1, created_at: "", layout_confirmed: true, output_sha256: "a"};
    expect(layoutReviewed(ws({reviews: [review]}), hwp)).toBe(true);
    expect(layoutReviewed(ws({reviews: [{...review, output_sha256: "b"}]}), hwp)).toBe(false);
    expect(layoutReviewed(ws({version: 2, reviews: [review]}), hwp)).toBe(false);
  });
});
