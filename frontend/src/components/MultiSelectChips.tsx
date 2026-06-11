"use client";

import { useState } from "react";

type Option = { value: string; label: string };

type Props = {
  name: string;
  options: Option[];
  selected: string[];
  /** 라벨이 길어 두 줄이상 차지하는 컬럼이면 false로 한 줄 표시 */
  inline?: boolean;
};

/**
 * 다중 선택 체크박스 + 칩 표시. form submit 시 같은 name으로 여러 hidden input을 보내
 * `?name=a&name=b` 형태로 URL에 직렬화됨.
 *
 * Server Component(부모 페이지)가 searchParams에서 string|string[]로 받음.
 */
export function MultiSelectChips({ name, options, selected, inline = true }: Props) {
  const [chosen, setChosen] = useState<Set<string>>(new Set(selected));

  const toggle = (v: string) => {
    setChosen((prev) => {
      const n = new Set(prev);
      if (n.has(v)) n.delete(v);
      else n.add(v);
      return n;
    });
  };

  return (
    <div className={inline ? "flex flex-wrap gap-2" : "flex flex-col gap-1.5"}>
      {options.map((o) => {
        const on = chosen.has(o.value);
        return (
          <label
            key={o.value}
            className={`inline-flex items-center gap-1.5 cursor-pointer select-none rounded border px-2 py-1 text-xs ${
              on
                ? "border-brand-500 bg-brand-500/15 text-brand-100"
                : "border-slate-700 bg-slate-950 text-slate-300 hover:border-slate-600"
            }`}
          >
            <input
              type="checkbox"
              className="sr-only"
              checked={on}
              onChange={() => toggle(o.value)}
            />
            {/* form submit 시 같은 name으로 hidden 전송 — 체크된 것만 */}
            {on ? <input type="hidden" name={name} value={o.value} /> : null}
            <span>{o.label}</span>
          </label>
        );
      })}
    </div>
  );
}
