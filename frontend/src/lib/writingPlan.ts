import {SourceDocument, WritingPlanItem} from "./workspace";
import {buildNoticeBrief} from "./noticeBrief";

export function suggestWritingTargets(documents: SourceDocument[]): WritingPlanItem[] {
  const result:WritingPlanItem[]=[];
  const names=new Set<string>();
  for(const excerpt of buildNoticeBrief(documents).submissions){
    const pattern=/정성\s*제안서|정량(?:적평가)?\s*제안서|제안\s*요약서|가격\s*입찰서|사용인감계|(?:청렴계약\s*)?이행각서|서약서|사업자등록증|법인등기부등본|주민등록등본|법인인감증명서|경쟁입찰참가자격등록증|중소기업\s*확인서|신용등급확인서/g;
    for(const match of excerpt.text.matchAll(pattern)){
      const prefix=excerpt.text.slice(0,match.index);
      if((prefix.match(/\(/g)?.length || 0) > (prefix.match(/\)/g)?.length || 0)) continue;
      const title=match[0], key=title.replace(/\s/g,"");
      if(names.has(key))continue;
      names.add(key);
      const issued=/등록증|등본|증명서|확인서/.test(title);
      result.push({id:`source-target-${result.length}`,title,document_id:excerpt.documentId,quote:excerpt.quote,
        document_kind:/정성/.test(title)?"qualitative_proposal":/가격/.test(title)?"bid_document":"other_document",
        action:issued?"attach":/가격/.test(title)?"electronic":"write"});
    }
  }
  return result;
}
