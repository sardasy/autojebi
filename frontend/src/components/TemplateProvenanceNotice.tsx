import {templateProvenanceWarning, type TemplateProvenance} from "@/lib/templateProvenance";

export default function TemplateProvenanceNotice({value, templateKey}: {value?: TemplateProvenance; templateKey?: string}) {
  const warning = templateProvenanceWarning(value, templateKey);
  if (!warning) return null;
  return <p role="status" aria-label="템플릿 출처" className="text-sm text-amber-800">{warning}</p>;
}
