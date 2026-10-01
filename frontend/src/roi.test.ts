import { describe, expect, it } from "vitest";
import { roiFromDrag } from "./roi";

describe("roiFromDrag", () => {
  it("normalizes a reverse drag", () => {
    expect(roiFromDrag({ x: 0.8, y: 0.7 }, { x: 0.2, y: 0.1 }))
      .toEqual([0.2, 0.1, 0.8, 0.7]);
  });

  it("clamps coordinates to the image", () => {
    expect(roiFromDrag({ x: -0.2, y: 0.25 }, { x: 1.4, y: 0.75 }))
      .toEqual([0, 0.25, 1, 0.75]);
  });

  it("rejects an accidental click", () => {
    expect(roiFromDrag({ x: 0.5, y: 0.5 }, { x: 0.501, y: 0.501 })).toBeNull();
  });
});
