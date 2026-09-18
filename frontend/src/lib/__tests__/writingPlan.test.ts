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
