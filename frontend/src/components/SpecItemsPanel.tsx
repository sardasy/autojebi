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

type Props = {
  notice: NoticeRecord;
  enabled: boolean;
};

const STATUS_OPTIONS: { value: SpecItemStatus; label: string }[] = [
  { value: "candidate", label: "후보" },
  { value: "reviewed", label: "검토" },
  { value: "matched", label: "대응" },
  { value: "gap", label: "차이" },
  { value: "ignored", label: "제외" },
];

export function SpecItemsPanel({ notice, enabled }: Props) {
  const [items, setItems] = useState<NoticeSpecItem[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [composeOpen, setComposeOpen] = useState(false);
  const [proposalOpen, setProposalOpen] = useState(false);
  const [pending, startTransition] = useTransition();
  const toast = useToast();
  const router = useRouter();

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
        if (alive) setItems([]);
      })
      .finally(() => {
        if (alive) setLoaded(true);
      });
    return () => {
      alive = false;
    };
  }, [enabled, notice.notice_no]);

  const extract = () => {
    startTransition(async () => {
      try {
        const result = await actionExtractSpecItems(notice.notice_no);
        setItems(result.items);
        toast.push("success", `규격 추출 완료: ${result.items.length}개 항목`);
        router.refresh();
      } catch (e) {
        toast.push("error", `규격 추출 실패: ${(e as Error).message}`);
      }
    });
  };

  const patch = (item: NoticeSpecItem, payload: Partial<NoticeSpecItem>) => {
    startTransition(async () => {
      try {
        const updated = await actionUpdateSpecItem(notice.notice_no, item.id, payload);
        setItems((current) => current.map((entry) => (entry.id === updated.id ? updated : entry)));
        toast.push("success", `${item.label} 저장`);
        router.refresh();
      } catch (e) {
        toast.push("error", `규격 항목 저장 실패: ${(e as Error).message}`);
      }
    });
  };

  return (
    <section
      id="spec-items"
      className="scroll-mt-24 space-y-2 rounded border border-slate-800 bg-slate-900/30 p-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-xs font-semibold text-slate-300">규격 항목</div>
          <p className="mt-1 text-xs text-slate-500">
            {items.length > 0
              ? `${items.length}개 항목을 HWP 규격대응표에 사용합니다.`
              : "규격 항목을 추출한 뒤 HWP 작성에 사용합니다."}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={extract}
            disabled={!enabled || pending}
            className="rounded border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50"
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
            className="rounded border border-brand-500 px-3 py-1.5 text-sm font-medium text-brand-100 hover:bg-brand-950/30 disabled:opacity-50"
          >
            제안서 HWP 작성
          </button>
        </div>
      </div>

      {!loaded ? (
        <div className="text-sm text-slate-500">규격 항목을 불러오는 중…</div>
      ) : items.length === 0 ? (
        <div className="rounded border border-dashed border-slate-700 p-3 text-sm text-slate-400">
          규격 항목이 없습니다. “규격 추출”을 실행하세요.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-slate-400">
              <tr>
                <th className="px-2 py-1 text-left">항목</th>
                <th className="px-2 py-1 text-left">요구값</th>
                <th className="px-2 py-1 text-left">제안/대응</th>
                <th className="px-2 py-1 text-left">상태</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className="border-t border-slate-800">
                  <td className="px-2 py-2 text-slate-100">
                    <div>{item.label}</div>
                    <div className="text-xs text-slate-500">{item.unit || item.category}</div>
                  </td>
                  <td className="px-2 py-2 text-slate-300">{item.required_value || "-"}</td>
                  <td className="px-2 py-2">
                    <input
                      defaultValue={item.proposed_value || ""}
                      onBlur={(e) => {
                        if (e.target.value !== (item.proposed_value || "")) {
                          patch(item, { proposed_value: e.target.value, status: "reviewed" });
                        }
                      }}
                      className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs"
                    />
                  </td>
                  <td className="px-2 py-2">
                    <select
                      value={item.status}
                      onChange={(e) => patch(item, { status: e.target.value as SpecItemStatus })}
                      className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs"
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
