"use client";

import { useMemo, useState, useTransition } from "react";

import {
  actionUpdateHwpMapping,
  actionUpdateHwpTemplate,
  actionUpsertHwpMapping,
  actionUpsertHwpTemplate,
} from "@/lib/actions";
import type {
  HwpMappingUpsertRequest,
  HwpTemplateRecord,
  HwpTemplateUpsertRequest,
  HwpTransform,
} from "@/lib/api";

const TRANSFORMS: HwpTransform[] = [
  "none",
  "date_yyyy_mm_dd",
  "number_comma",
  "business_number_dash",
  "strip",
  "truncate_1000",
];

const emptyTemplate: HwpTemplateUpsertRequest = {
  template_key: "",
  kind: "bid_form",
  name: "",
  template_path: "",
  template_version: "",
  active: true,
};

const emptyMapping: HwpMappingUpsertRequest = {
  hwp_field_name: "",
  context_path: "company.company_name",
  value_type: "string",
  required: false,
  default_value: "",
  transform: "none",
  sort_order: 10,
  active: true,
};

export function HwpMappingAdmin({
  initialTemplates,
}: {
  initialTemplates: HwpTemplateRecord[];
}) {
  const [templates, setTemplates] = useState(initialTemplates);
  const [selectedId, setSelectedId] = useState<number | null>(
    initialTemplates[0]?.id ?? null,
  );
  const [templateForm, setTemplateForm] = useState<HwpTemplateUpsertRequest>(
    initialTemplates[0] ? templateToForm(initialTemplates[0]) : emptyTemplate,
  );
  const [editingMappingId, setEditingMappingId] = useState<number | null>(null);
  const [mappingForm, setMappingForm] = useState<HwpMappingUpsertRequest>(emptyMapping);
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const selected = useMemo(
    () => templates.find((item) => item.id === selectedId) ?? null,
    [selectedId, templates],
  );

  function selectTemplate(template: HwpTemplateRecord) {
    setSelectedId(template.id);
    setTemplateForm(templateToForm(template));
    setEditingMappingId(null);
    setMappingForm(emptyMapping);
    setMessage(null);
  }

  function replaceTemplate(next: HwpTemplateRecord) {
    setTemplates((items) => {
      const exists = items.some((item) => item.id === next.id);
      if (!exists) return [...items, next].sort((a, b) => a.template_key.localeCompare(b.template_key));
      return items.map((item) => (item.id === next.id ? next : item));
    });
    setSelectedId(next.id);
    setTemplateForm(templateToForm(next));
  }

  function saveTemplate() {
    startTransition(async () => {
      try {
        const payload = normalizeTemplate(templateForm);
        const next = selected?.id
          ? await actionUpdateHwpTemplate(selected.id, {
              kind: payload.kind,
              name: payload.name,
              template_path: payload.template_path,
              template_version: payload.template_version,
              active: payload.active,
            })
          : await actionUpsertHwpTemplate(payload);
        replaceTemplate(next);
        setMessage("템플릿이 저장됐습니다.");
      } catch (e) {
        setMessage((e as Error).message);
      }
    });
  }

  function newTemplate() {
    setSelectedId(null);
    setTemplateForm(emptyTemplate);
    setEditingMappingId(null);
    setMappingForm(emptyMapping);
    setMessage(null);
  }

  function disableTemplate() {
    if (!selected?.id) return;
    startTransition(async () => {
      try {
        const next = await actionUpdateHwpTemplate(selected.id, { active: false });
        replaceTemplate(next);
        setMessage("템플릿을 비활성화했습니다.");
      } catch (e) {
        setMessage((e as Error).message);
      }
    });
  }

  function editMapping(mapping: HwpTemplateRecord["mappings"][number]) {
    setEditingMappingId(mapping.id ?? null);
    setMappingForm({
      hwp_field_name: mapping.hwp_field_name,
      context_path: mapping.context_path,
      value_type: mapping.value_type,
      required: mapping.required,
      default_value: mapping.default_value ?? "",
      transform: mapping.transform as HwpTransform,
      sort_order: mapping.sort_order,
      active: mapping.active,
    });
    setMessage(null);
  }

  function saveMapping() {
    if (!selected?.id) {
      setMessage("먼저 템플릿을 저장하세요.");
      return;
    }
    startTransition(async () => {
      try {
        const payload = normalizeMapping(mappingForm);
        const next =
          editingMappingId === null
            ? await actionUpsertHwpMapping(selected.id, payload)
            : await actionUpdateHwpMapping(selected.id, editingMappingId, payload);
        replaceTemplate(next);
        setEditingMappingId(null);
        setMappingForm(emptyMapping);
        setMessage("필드 매핑이 저장됐습니다.");
      } catch (e) {
        setMessage((e as Error).message);
      }
    });
  }

  function disableMapping(mappingId: number) {
    if (!selected?.id) return;
    startTransition(async () => {
      try {
        const next = await actionUpdateHwpMapping(selected.id, mappingId, {
          active: false,
        });
        replaceTemplate(next);
        setEditingMappingId(null);
        setMappingForm(emptyMapping);
        setMessage("필드 매핑을 비활성화했습니다.");
      } catch (e) {
        setMessage((e as Error).message);
      }
    });
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[280px_1fr]">
      <aside className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-200">템플릿</h3>
          <button
            type="button"
            onClick={newTemplate}
            className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-200 hover:border-slate-500"
          >
            새 템플릿
          </button>
        </div>
        <div className="space-y-2">
          {templates.length === 0 ? (
            <p className="rounded border border-slate-800 bg-slate-950/50 p-3 text-sm text-slate-500">
              등록된 HWP 템플릿 없음
            </p>
          ) : (
            templates.map((template) => (
              <button
                key={template.id}
                type="button"
                onClick={() => selectTemplate(template)}
                className={`block w-full rounded border p-3 text-left text-sm ${
                  selectedId === template.id
                    ? "border-brand-500 bg-brand-500/10 text-slate-100"
                    : "border-slate-800 bg-slate-950/40 text-slate-300 hover:border-slate-600"
                }`}
              >
                <span className="block font-medium">{template.name}</span>
                <span className="mt-1 block text-xs text-slate-500">
                  {template.template_key} · {template.kind}
                </span>
              </button>
            ))
          )}
        </div>
      </aside>

      <div className="space-y-5">
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="template_key">
            <input
              value={templateForm.template_key}
              disabled={Boolean(selected)}
              onChange={(e) =>
                setTemplateForm((prev) => ({ ...prev, template_key: e.target.value }))
              }
              className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 disabled:text-slate-500"
              placeholder="bid_form"
            />
          </Field>
          <Field label="종류">
            <select
              value={templateForm.kind}
              onChange={(e) =>
                setTemplateForm((prev) => ({
                  ...prev,
                  kind: e.target.value as HwpTemplateUpsertRequest["kind"],
                }))
              }
              className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
            >
              <option value="bid_form">입찰양식</option>
              <option value="proposal">제안서</option>
            </select>
          </Field>
          <Field label="이름">
            <input
              value={templateForm.name}
              onChange={(e) =>
                setTemplateForm((prev) => ({ ...prev, name: e.target.value }))
              }
              className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
              placeholder="입찰참가신청서"
            />
          </Field>
          <Field label="버전">
            <input
              value={templateForm.template_version ?? ""}
              onChange={(e) =>
                setTemplateForm((prev) => ({ ...prev, template_version: e.target.value }))
              }
              className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
              placeholder="put_fields_v1"
            />
          </Field>
          <Field label="템플릿 경로">
            <input
              value={templateForm.template_path}
              onChange={(e) =>
                setTemplateForm((prev) => ({ ...prev, template_path: e.target.value }))
              }
              className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
              placeholder="templates/form.hwp"
            />
          </Field>
          <label className="flex items-end gap-2 pb-2 text-sm text-slate-300">
            <input
              type="checkbox"
              checked={templateForm.active ?? true}
              onChange={(e) =>
                setTemplateForm((prev) => ({ ...prev, active: e.target.checked }))
              }
              className="h-4 w-4 rounded border-slate-700 bg-slate-950"
            />
            사용
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={saveTemplate}
            disabled={isPending}
            className="rounded bg-brand-500 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-60"
          >
            템플릿 저장
          </button>
          {selected ? (
            <button
              type="button"
              onClick={disableTemplate}
              disabled={isPending}
              className="rounded border border-amber-700 px-3 py-2 text-sm text-amber-200 hover:border-amber-500 disabled:opacity-60"
            >
              템플릿 비활성화
            </button>
          ) : null}
          {message ? <span className="text-sm text-slate-400">{message}</span> : null}
        </div>

        <div className="border-t border-slate-800 pt-5">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-slate-200">필드 매핑</h3>
            <button
              type="button"
              onClick={() => {
                setEditingMappingId(null);
                setMappingForm(emptyMapping);
              }}
              className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-200 hover:border-slate-500"
            >
              새 필드
            </button>
          </div>

          <div className="overflow-x-auto rounded border border-slate-800">
            <table className="min-w-full divide-y divide-slate-800 text-sm">
              <thead className="bg-slate-950/70 text-xs text-slate-400">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">HWP 필드</th>
                  <th className="px-3 py-2 text-left font-medium">Context</th>
                  <th className="px-3 py-2 text-left font-medium">Transform</th>
                  <th className="px-3 py-2 text-left font-medium">상태</th>
                  <th className="px-3 py-2 text-right font-medium">작업</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {selected?.mappings.length ? (
                  selected.mappings.map((mapping) => (
                    <tr key={mapping.id ?? mapping.hwp_field_name} className="text-slate-200">
                      <td className="px-3 py-2 font-medium">{mapping.hwp_field_name}</td>
                      <td className="px-3 py-2 text-slate-400">{mapping.context_path}</td>
                      <td className="px-3 py-2 text-slate-400">{mapping.transform}</td>
                      <td className="px-3 py-2">
                        {mapping.required ? (
                          <span className="rounded bg-amber-500/10 px-2 py-1 text-xs text-amber-200">
                            필수
                          </span>
                        ) : (
                          <span className="text-xs text-slate-500">선택</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button
                          type="button"
                          onClick={() => editMapping(mapping)}
                          className="mr-2 rounded border border-slate-700 px-2 py-1 text-xs text-slate-200 hover:border-slate-500"
                        >
                          수정
                        </button>
                        {mapping.id ? (
                          <button
                            type="button"
                            onClick={() => disableMapping(mapping.id!)}
                            className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-400 hover:border-amber-600 hover:text-amber-200"
                          >
                            비활성화
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} className="px-3 py-6 text-center text-sm text-slate-500">
                      등록된 필드 매핑 없음
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <Field label="HWP 필드명">
              <input
                value={mappingForm.hwp_field_name}
                onChange={(e) =>
                  setMappingForm((prev) => ({ ...prev, hwp_field_name: e.target.value }))
                }
                className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                placeholder="company_name"
              />
            </Field>
            <Field label="Context path">
              <input
                value={mappingForm.context_path}
                onChange={(e) =>
                  setMappingForm((prev) => ({ ...prev, context_path: e.target.value }))
                }
                className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                placeholder="company.company_name"
              />
            </Field>
            <Field label="Transform">
              <select
                value={mappingForm.transform}
                onChange={(e) =>
                  setMappingForm((prev) => ({
                    ...prev,
                    transform: e.target.value as HwpTransform,
                  }))
                }
                className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
              >
                {TRANSFORMS.map((transform) => (
                  <option key={transform} value={transform}>
                    {transform}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="기본값">
              <input
                value={mappingForm.default_value ?? ""}
                onChange={(e) =>
                  setMappingForm((prev) => ({ ...prev, default_value: e.target.value }))
                }
                className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
              />
            </Field>
            <Field label="정렬">
              <input
                type="number"
                value={mappingForm.sort_order ?? 0}
                onChange={(e) =>
                  setMappingForm((prev) => ({
                    ...prev,
                    sort_order: Number(e.target.value || 0),
                  }))
                }
                className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
              />
            </Field>
            <label className="flex items-end gap-2 pb-2 text-sm text-slate-300">
              <input
                type="checkbox"
                checked={Boolean(mappingForm.required)}
                onChange={(e) =>
                  setMappingForm((prev) => ({ ...prev, required: e.target.checked }))
                }
                className="h-4 w-4 rounded border-slate-700 bg-slate-950"
              />
              필수
            </label>
          </div>

          <button
            type="button"
            onClick={saveMapping}
            disabled={isPending || !selected}
            className="mt-3 rounded bg-brand-500 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-60"
          >
            {editingMappingId === null ? "필드 추가" : "필드 저장"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-medium text-slate-400">{label}</span>
      {children}
    </label>
  );
}

function templateToForm(template: HwpTemplateRecord): HwpTemplateUpsertRequest {
  return {
    template_key: template.template_key,
    kind: template.kind,
    name: template.name,
    template_path: template.template_path,
    template_version: template.template_version ?? "",
    active: template.active,
  };
}

function normalizeTemplate(form: HwpTemplateUpsertRequest): HwpTemplateUpsertRequest {
  return {
    ...form,
    template_key: form.template_key.trim(),
    name: form.name.trim(),
    template_path: form.template_path.trim(),
    template_version: form.template_version?.trim() || null,
    active: form.active ?? true,
  };
}

function normalizeMapping(form: HwpMappingUpsertRequest): HwpMappingUpsertRequest {
  return {
    ...form,
    hwp_field_name: form.hwp_field_name.trim(),
    context_path: form.context_path.trim(),
    value_type: form.value_type?.trim() || "string",
    default_value: form.default_value?.trim() || null,
    transform: form.transform ?? "none",
    sort_order: Number(form.sort_order ?? 0),
    active: form.active ?? true,
  };
}
