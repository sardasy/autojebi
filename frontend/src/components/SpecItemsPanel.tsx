"use client";

import { useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import {
  actionExtractSpecItems,
  actionListSpecItems,
  actionUpdateSpecItem,
} from "@/lib/actions";
import type { NoticeRecord, NoticeSpecItem, SpecItemStatus } from "@/lib/api";
import { HwpComposeDialog } from "./HwpComposeDialog";
import { ProposalComposeDialog } from "./ProposalComposeDialog";
import { useToast } from "./Toast";
import { ActionFeedback } from "./ActionFeedback";

type Props = {
  notice: NoticeRecord;
  enabled: boolean;
  mode?: "spec" | "proposal";
};

const STATUS_OPTIONS: { value: SpecItemStatus; label: string }[] = [
  { value: "candidate", label: "후보" },
  { value: "reviewed", label: "검토" },
  { value: "matched", label: "대응" },
  { value: "gap", label: "차이" },
  { value: "ignored", label: "제외" },
];

export function SpecItemsPanel({ notice, enabled, mode = "spec" }: Props) {
  const [items, setItems] = useState<NoticeSpecItem[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [composeOpen, setComposeOpen] = useState(false);
  const [proposalOpen, setProposalOpen] = useState(false);
  const [pending, startTransition] = useTransition();
  const toast = useToast();
  const router = useRouter();
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!enabled) {
      setLoaded(true);
      return;
    }
    let alive = true;
    actionListSpecItems(notice.notice_no)
      .then((result) => {
        if (alive) setItems(result.items);
      })
      .catch(() => {
        if (alive) setError("규격을 불러오지 못했습니다. 새로고침 후 다시 확인하세요.");
      })
      .finally(() => {
        if (alive) setLoaded(true);
      });
    return () => {
      alive = false;
    };
  }, [enabled, notice.notice_no]);

  const extract = () => {
    setMessage("규격 추출 중"); setError("");
    startTransition(async () => {
      try {
        const result = await actionExtractSpecItems(notice.notice_no);
        setItems(result.items);
        setMessage(`추출 완료: 요구값 ${result.items.filter(i => i.required_value?.trim()).length}개 · 전체 후보 ${result.items.length}개`);
        toast.push("success", `규격 추출 완료: ${result.items.length}개 항목`);
        router.refresh();
      } catch (e) {
        setMessage("규격 추출 실패. 첨부파일과 연결 상태를 확인한 뒤 다시 실행하세요."); setError((e as Error).message);
        toast.push("error", `규격 추출 실패: ${(e as Error).message}`);
      }
    });
  };

  const patch = (item: NoticeSpecItem, payload: Partial<NoticeSpecItem>) => {
    startTransition(async () => {
      try {
        const updated = await actionUpdateSpecItem(notice.notice_no, item.id, payload);
        setItems((current) => current.map((entry) => (entry.id === updated.id ? updated : entry)));
        setMessage(`${item.label} 저장 완료`); setError("");
        toast.push("success", `${item.label} 저장`);
        router.refresh();
      } catch (e) {
        setMessage("저장 실패. 입력값을 확인하고 다시 시도하세요."); setError((e as Error).message);
        toast.push("error", `규격 항목 저장 실패: ${(e as Error).message}`);
      }
    });
  };

  return (
    <section
      id="spec-items"
      className="scroll-mt-24 space-y-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="font-semibold text-slate-700">{mode === "proposal" ? "제안서 문서 생성" : "규격 대응"}</h2>
          <p className="mt-1 text-xs text-slate-500">
            요구값 확인 {items.filter(i => i.required_value?.trim()).length}개 · 빈 후보 {items.filter(i => !i.required_value?.trim()).length}개
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={extract}
            disabled={!enabled || pending}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-800 hover:bg-slate-100 disabled:opacity-50"
          >
            규격 추출
          </button>
          <button
            type="button"
            onClick={() => setComposeOpen(true)}
            disabled={!enabled || pending || items.length === 0}
            className="rounded bg-brand-500 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            HWP 작성
          </button>
          <button
            type="button"
            onClick={() => setProposalOpen(true)}
            disabled={!enabled || pending || items.length === 0}
            className="rounded border border-brand-500 px-3 py-1.5 text-sm font-medium text-brand-700 hover:bg-red-50/30 disabled:opacity-50"
          >
            제안서 HWP 작성
          </button>
        </div>
      </div>

      <ActionFeedback message={message || error} detail={error} error={Boolean(error)}/>
      {mode === "proposal" ? null : !loaded ? (
        <div className="text-sm text-slate-500">규격 항목을 불러오는 중…</div>
      ) : items.length === 0 ? (
        <div className="rounded border border-dashed border-slate-300 p-3 text-sm text-slate-600">
          규격 항목이 없습니다. “규격 추출”을 실행하세요.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="work-table">
            <thead className="text-xs text-slate-600">
              <tr>
                <th className="px-2 py-1 text-left">항목</th>
                <th className="px-2 py-1 text-left">요구값</th>
                <th className="px-2 py-1 text-left">제안/대응</th>
                <th className="px-2 py-1 text-left">근거</th>
                <th className="px-2 py-1 text-left">상태</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className="border-t border-slate-200">
                  <td className="px-2 py-2 text-slate-900">
                    <div>{item.label}</div>
                    <div className="text-xs text-slate-500">{item.unit || item.category}</div>
                  </td>
                  <td className="px-2 py-2 text-slate-700">{item.required_value || "-"}</td>
                  <td className="px-2 py-2">
                    <input
                      aria-label={`${item.label} 제안값`}
                      defaultValue={item.proposed_value || ""}
                      onBlur={(e) => {
                        if (e.target.value !== (item.proposed_value || "")) {
                          patch(item, { proposed_value: e.target.value, status: "reviewed" });
                        }
                      }}
                      className="w-full rounded border border-slate-300 bg-white px-2 py-1 text-xs"
                    />
                  </td>
                  <td className="max-w-64 px-2 py-2 text-xs text-slate-600">{item.source_text || (typeof item.evidence?.text === "string" ? item.evidence.text : "근거 미확인")}<div>{item.source_file_name}{item.source_page ? ` · ${item.source_page}쪽` : ""}</div></td>
                  <td className="px-2 py-2">
                    <select
                      aria-label={`${item.label} 검토 상태`}
                      value={item.status}
                      onChange={(e) => patch(item, { status: e.target.value as SpecItemStatus })}
                      className="rounded border border-slate-300 bg-white px-2 py-1 text-xs"
                    >
                      {STATUS_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <HwpComposeDialog
        open={composeOpen}
        onClose={() => setComposeOpen(false)}
        notice={notice}
        specItems={items}
      />
      <ProposalComposeDialog
        open={proposalOpen}
        onClose={() => setProposalOpen(false)}
        notice={notice}
        specItems={items}
      />
    </section>
  );
}
