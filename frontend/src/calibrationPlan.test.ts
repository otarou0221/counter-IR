import { describe, expect, it } from "vitest";
import { buildCalibrationPlan } from "./calibrationPlan";
import type { RoiReferenceCapture, SystemSettings } from "./types";

describe("settings calibration plan", () => {
  it("calibrates active cameras with an empty reference and reports the rest", () => {
    const settings = {
      cameras: [
        { camera_id: "camera_1" },
        { camera_id: "camera_2" },
        { camera_id: "camera_3" },
      ],
      pallets: [
        { camera_id: "camera_1", enabled: true },
        { camera_id: "camera_2", enabled: true },
        { camera_id: "camera_3", enabled: false },
      ],
    } as SystemSettings;
    const references = [
      { camera_id: "camera_1", capture_id: "empty_1", rgb_path: "rgb.jpg" },
      { camera_id: "camera_3", capture_id: "empty_3", rgb_path: "rgb.jpg" },
    ] as RoiReferenceCapture[];

    expect(buildCalibrationPlan(settings, references)).toEqual({
      readyCameraIds: ["camera_1"],
      missingReferenceCameraIds: ["camera_2"],
    });
  });

  it("does not calibrate a disabled camera even when it has a saved image", () => {
    const settings = {
      cameras: [{ camera_id: "camera_1" }, { camera_id: "camera_2" }],
      pallets: [
        { camera_id: "camera_1", enabled: true },
        { camera_id: "camera_2", enabled: false },
      ],
    } as SystemSettings;
    const references = [
      { camera_id: "camera_2", capture_id: "empty_2", rgb_path: "rgb.jpg" },
    ] as RoiReferenceCapture[];

    expect(buildCalibrationPlan(settings, references)).toEqual({
      readyCameraIds: [],
      missingReferenceCameraIds: ["camera_1"],
    });
  });
});
