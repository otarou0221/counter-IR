import { describe, expect, it } from "vitest";
import { remoteResourceStatus } from "./remoteResource";

describe("remote resource status", () => {
  it("distinguishes initial loading, initial failure, ready, and stale data", () => {
    expect(remoteResourceStatus(null, null)).toBe("loading");
    expect(remoteResourceStatus(null, "通信失敗")).toBe("error");
    expect(remoteResourceStatus({}, null)).toBe("ready");
    expect(remoteResourceStatus({}, "更新失敗")).toBe("stale");
  });
});
