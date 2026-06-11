"use client";

import { useMemo, useState, useTransition } from "react";

import { actionAutofill } from "@/lib/actions";
import type { NoticeRecord } from "@/lib/api";
import { Modal } from "./Modal";
import { useToast } from "./Toast";

type Props = {
  open: boolean;
  onClose: () => void;
  notice: NoticeRecord;
};

const DEFAULT_VALUES = {
  company_name: "미림씨스콘",
  business_number: "",
  ceo_name: "",
  address: "",
};

function isUnsafePath(p: string): boolean {
  if (!p) return true;
  // 절대 경로 또는 traversal 차단
  if (p.startsWith("/") || /^[A-Za-z]:[\\/]/.test(p)) return true;
  if (p.includes("..")) return true;
  return false;
}

export function AutofillDialog({ open, onClose, notice }: Props) {
  const [templatePath, setTemplatePath] = useState(
    "templates/입찰참가신청서_양식.hwp",
  );
  const [outputPath, setOutputPath] = useState(
    `output/autofilled_${notice.notice_no}.hwp`,
  );
  const [visible, setVisible] = useState(false);
  const [valuesText, setValuesText] = useState(
    JSON.stringify(DEFAULT_VALUES, null, 2),
  );
  const [pending, startTransition] = useTransition();
  const toast = useToast();

  const validation = useMemo(() => {
    const errors: string[] = [];
    if (isUnsafePath(templatePath)) {
      errors.push("template_path는 상대 경로여야 하며 '..' 금지");
    }
    if (isUnsafePath(outputPath)) {
      errors.push("output_path는 상대 경로여야 하며 '..' 금지");
    }
    let values: Record<string, string> | null = null;
    try {
      const parsed = valuesText.trim() ? JSON.parse(valuesText) : {};
      if (typeof parsed !== "object" || Array.isArray(parsed)) {
        errors.push("values는 JSON 객체여야 합니다");
      } else {
        values = Object.fromEntries(
          Object.entries(parsed as Record<string, unknown>).map(([k, v]) => [
            k,
            String(v ?? ""),
          ]),
        );
      }
    } catch (e) {
      errors.push(`values JSON 파싱 실패: ${(e as Error).message}`);
    }
    return { errors, values };
  }, [templatePath, outputPath, valuesText]);

  const submit = () => {
    if (validation.errors.length > 0 || !validation.values) {
      toast.push("error", validation.errors.join("\n"));
      return;
    }
    const payload = {
      template_path: templatePath,
      output_path: outputPath,
      values: validation.values,
      visible,
    };
    startTransition(async () => {
      try {
        const r = await actionAutofill(notice.notice_no, payload);
        const remaining = r.remaining_placeholders.length;
        if (remaining > 0) {
          toast.push(
            "info",
            `Autofill 완료 (남은 placeholder ${remaining}개)\n` +
              `output: ${r.output_path}\nremaining: ${r.remaining_placeholders.join(", ")}`,
          );
        } else {
          toast.push(
            "success",
            `Autofill 완료 — replaced ${r.replaced.length}개\noutput: ${r.output_path}`,
          );
        }
        onClose();
      } catch (e) {
        toast.push("error", `Autofill 실패: ${(e as Error).message}`);
      }
    });
  };

  return (
    <Modal open={open} onClose={onClose} title="HWP 양식 자동채움" size="lg">
      <div className="space-y-4">
        <p className="text-sm text-slate-300">
          milim-hwp-agent에 위임. 회사 기본값은 env에서 가져오고{" "}
          <code className="bg-slate-800 px-1 rounded">values</code>가 위에 덮어쓰기.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Field label="template_path (상대경로)">
            <input
              type="text"
              value={templatePath}
              onChange={(e) => setTemplatePath(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-sm font-mono"
            />
          </Field>
          <Field label="output_path (상대경로)">
            <input
              type="text"
              value={outputPath}
              onChange={(e) => setOutputPath(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-sm font-mono"
            />
          </Field>
        </div>

        <Field label="values (JSON, env 기본값 위에 덮어쓰기)">
          <textarea
            value={valuesText}
            onChange={(e) => setValuesText(e.target.value)}
            rows={8}
            className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs font-mono"
            spellCheck={false}
          />
        </Field>

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={visible}
            onChange={(e) => setVisible(e.target.checked)}
            className="accent-brand-500"
          />
          <span>HWP 창 표시 (디버그)</span>
        </label>

        {validation.errors.length > 0 ? (
          <ul className="text-xs text-red-400 list-disc pl-4">
            {validation.errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        ) : null}

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={pending}
            className="rounded border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800"
          >
            취소
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={pending || validation.errors.length > 0}
            className="rounded bg-brand-500 hover:bg-brand-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            {pending ? "실행 중…" : "실행"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="block text-xs text-slate-400 mb-1">{label}</span>
      {children}
    </label>
  );
}
