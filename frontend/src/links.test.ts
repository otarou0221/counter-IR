import { describe, expect, it } from "vitest";
import { artifactUrl } from "./links";

describe("artifactUrl", () => {
  it("keeps path separators and encodes Japanese names", () => {
    expect(artifactUrl("measurements/測定1/plot.html"))
      .toBe("/artifacts/measurements/%E6%B8%AC%E5%AE%9A1/plot.html");
  });
});

