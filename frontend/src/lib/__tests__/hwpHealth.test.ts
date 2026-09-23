import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";
import {pollHwpHealth, type HwpHealthState} from "../hwpHealth";
import {workspaceFetch} from "../workspace";

vi.mock("../workspace", () => ({workspaceFetch: vi.fn()}));
const response = (code: string) => ({ok: true, json: async () => ({code})}) as Response;
describe("HWP diagnostic polling deadlines", () => {
  beforeEach(() => {vi.useFakeTimers(); vi.clearAllMocks();});
  afterEach(() => {vi.useRealTimers();});
  it("cancels a hanging body in five seconds, serializes refresh and backs off", async () => {
    const updates: HwpHealthState[] = [];
    vi.mocked(workspaceFetch).mockResolvedValue({ok: true, json: () => new Promise(() => {})} as Response);
    const poll = pollHwpHealth(s => updates.push(s));
    poll.refresh(); poll.refresh();
    expect(workspaceFetch).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(4999);
    expect(updates).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(1);
    expect(updates[0].error).toBe("worker_timeout");
    expect(vi.mocked(workspaceFetch).mock.calls[0][1]?.signal?.aborted).toBe(true);
    await vi.advanceTimersByTimeAsync(2999);
    expect(workspaceFetch).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(workspaceFetch).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(5000 + 5999);
    expect(workspaceFetch).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(1);
    expect(workspaceFetch).toHaveBeenCalledTimes(3);
    poll.stop();
    expect(vi.getTimerCount()).toBe(0);
  });
  it("retains last successful state as stale and resets backoff after recovery", async () => {
    const updates: HwpHealthState[] = [];
    vi.mocked(workspaceFetch).mockResolvedValueOnce(response("worker_running"))
      .mockRejectedValueOnce(new Error("diagnostic_failed")).mockResolvedValue(response("worker_recovery"));
    const poll = pollHwpHealth(s => updates.push(s));
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(3000);
    expect(updates[1].stale).toBe(true);
    expect(updates[1].status.code).toBe("worker_running");
    expect(updates[1].checkedAt).toBe(updates[0].checkedAt);
    await vi.advanceTimersByTimeAsync(3000);
    expect(updates[2].status.code).toBe("worker_recovery");
    expect(updates[2].stale).toBe(false);
    await vi.advanceTimersByTimeAsync(3000);
    expect(workspaceFetch).toHaveBeenCalledTimes(4);
    poll.stop();
  });
  it("caps backoff at thirty seconds and polls configuration errors every thirty seconds", async () => {
    vi.mocked(workspaceFetch).mockResolvedValue(response("worker_timeout"));
    const poll = pollHwpHealth(() => {});
    await vi.advanceTimersByTimeAsync(0);
    for (const delay of [3000, 6000, 12000, 24000, 30000, 30000]) {
      const previous = vi.mocked(workspaceFetch).mock.calls.length;
      await vi.advanceTimersByTimeAsync(delay - 1);
      expect(workspaceFetch).toHaveBeenCalledTimes(previous);
      await vi.advanceTimersByTimeAsync(1);
      expect(workspaceFetch).toHaveBeenCalledTimes(previous + 1);
    }
    vi.mocked(workspaceFetch).mockResolvedValue(response("worker_auth"));
    await vi.advanceTimersByTimeAsync(30000);
    const count = vi.mocked(workspaceFetch).mock.calls.length;
    await vi.advanceTimersByTimeAsync(29999);
    expect(workspaceFetch).toHaveBeenCalledTimes(count);
    poll.stop();
  });
});
