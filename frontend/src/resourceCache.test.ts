import { describe, expect, it } from "vitest";
import { ResourceCache } from "./resourceCache";

describe("ResourceCache", () => {
  it("上限を超えた時に最も古い要素を破棄する", () => {
    const cache = new ResourceCache<number>(2);
    cache.set("first", 1);
    cache.set("second", 2);
    cache.set("third", 3);

    expect(cache.peek("first")).toBeUndefined();
    expect(cache.peek("second")).toBe(2);
    expect(cache.peek("third")).toBe(3);
  });

  it("取得した要素を最近使用したものとして残す", () => {
    const cache = new ResourceCache<number>(2);
    cache.set("first", 1);
    cache.set("second", 2);
    expect(cache.get("first")).toBe(1);
    cache.set("third", 3);

    expect(cache.peek("first")).toBe(1);
    expect(cache.peek("second")).toBeUndefined();
  });

  it("無効な上限を拒否する", () => {
    expect(() => new ResourceCache(0)).toThrow("1以上の整数");
  });
});
