import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { DemoReadinessPanel } from "../DemoReadinessPanel";

it("does not claim real integration success from registered settings", () => {
  render(<DemoReadinessPanel
    health={{ok:true, checks:{db:"ok", DATA_GO_KR_API_KEY:"ok", QDRANT_URL:"ok"}}}
    healthError={null} hwpHealth={{ok:true, base_url:"http://127.0.0.1:8000"}} hwpHealthError={null}
    hwpTemplates={[1,2].map(id => ({id, template_key:`template-${id}`, kind:"bid_form", name:"Template", template_path:"missing.hwp", active:true, mappings:[]}))}
  />);
  expect(screen.getByRole("status")).toHaveTextContent("실작업 검증 별도");
  expect(screen.queryByText("실연동 데모 준비 완료")).not.toBeInTheDocument();
  expect(screen.getByText("G2B API 키 설정")).toBeInTheDocument();
  expect(screen.getByText("HWP 템플릿/매핑 등록")).toBeInTheDocument();
});
