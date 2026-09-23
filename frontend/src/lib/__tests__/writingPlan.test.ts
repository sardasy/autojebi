import {expect,it} from "vitest";
import {suggestWritingTargets} from "../writingPlan";
import {SourceDocument} from "../workspace";

it("has no generic targets without source submissions",()=>{
  expect(suggestWritingTargets([])).toEqual([]);
});
it("keeps actual source titles and uses the explicit registration submission",()=>{
  const source:SourceDocument={id:"notice",name:"입찰공고.hwp",role:"notice_source",confirmed:false,text_origin:"extracted",text:"① 사용인감계 1부(경쟁입찰참가자격등록증에 미등록 시)\n② 경쟁입찰참가자격등록증 1부\n③ 정성제안서 1부\n④ 서약서 1부"};
  const items=suggestWritingTargets([source]);
  expect(items.map(i=>i.title)).toEqual(["사용인감계","경쟁입찰참가자격등록증","정성제안서","서약서"]);
  expect(items[1].quote).toBe("② 경쟁입찰참가자격등록증 1부");
  expect(items[1].action).toBe("attach");
  expect(items[2].action).toBe("write");
  expect(suggestWritingTargets([{...source,role:"company_reference"}])).toEqual([]);
});
it("suggests a generic proposal and spaced issued document without splitting its conditional alternative",()=>{
  const text="나. 제안서 제출 서류\n\n1. 제안서 2식\n\n2. 법인 등기부등본(개인사업자인 경우 사업자등록증) 2부.";
  const source:SourceDocument={id:"notice",name:"시험공고.hwp",role:"notice_source",confirmed:false,text_origin:"hwp_ole",text};
  const items=suggestWritingTargets([source]);
  expect(items.map(i=>[i.title,i.action,i.document_kind])).toEqual([
    ["제안서","write","qualitative_proposal"], ["법인 등기부등본","attach","other_document"],
  ]);
  expect(items[1].quote).toContain("개인사업자인 경우 사업자등록증");
  for(const item of items) expect(text).toContain(item.quote);
});
it("uses explicitly headed table rows and keeps the condition in every suggested target",()=>{
  const text="제안서 접수 시 제출 자료\n\n순번\n\n구 성 내 용\n\n비 고\n\n1\n\n재무제표(최근 2년)\n\n2부\n\n2\n\n재직증명서, 위임장\n\n각 1부\n\n3\n\n청렴계약 이행각서\n\n지정 서식\n\n※ 제출 방법 확인";
  const source:SourceDocument={id:"rfp",name:"시험요청서.hwp",role:"notice_source",confirmed:false,text_origin:"hwp_ole",text};
  const items=suggestWritingTargets([source]);
  expect(items.map(i=>[i.title,i.action])).toEqual([["재무제표","attach"],["재직증명서","attach"],["위임장","write"],["청렴계약 이행각서","write"]]);
  expect(items[0].quote).toContain("최근 2년");
  for(const item of items) expect(text).toContain(item.quote);
});
it.each(["카달로그", "카탈로그"])("preserves the source spelling of 제품 %s",word=>{
  const text=`제안서 접수 시 제출 자료\n순번\n구 성 내 용\n비 고\n1\n제품 ${word}\n2부\n※ 안내`;
  const source:SourceDocument={id:"rfp",name:"시험요청서.hwp",role:"notice_source",confirmed:false,text_origin:"hwp_ole",text};
  const items=suggestWritingTargets([source]);
  expect(items.map(i=>[i.title,i.action])).toEqual([[`제품 ${word}`,"attach"]]);
  expect(text).toContain(items[0].quote);
});
