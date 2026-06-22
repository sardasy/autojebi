import "@testing-library/jest-dom";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

const navigationMocks = vi.hoisted(() => ({
  refresh: vi.fn(),
  push: vi.fn(),
  replace: vi.fn(),
  prefetch: vi.fn(),
  back: vi.fn(),
  forward: vi.fn(),
}));

(globalThis as typeof globalThis & {
  __routerRefreshMock?: typeof navigationMocks.refresh;
}).__routerRefreshMock = navigationMocks.refresh;

vi.mock("next/navigation", () => ({
  useRouter: () => navigationMocks,
}));

afterEach(() => {
  cleanup();
  navigationMocks.refresh.mockClear();
  navigationMocks.push.mockClear();
  navigationMocks.replace.mockClear();
  navigationMocks.prefetch.mockClear();
  navigationMocks.back.mockClear();
  navigationMocks.forward.mockClear();
});
