import type { SystemSettings } from "./types";

export type MeasurementFieldErrors = Partial<Record<
  "monitor_interval_seconds" | "pallet_height_mm" | "frame_count"
  | "measurement_frame_count" | "measurement_concurrency" | "warmup_frames"
  | "grid_mm" | "occupied_height_mm",
  string
>>;

export function measurementFieldErrors(settings: SystemSettings): MeasurementFieldErrors {
  const errors: MeasurementFieldErrors = {};
  if (!integerInRange(settings.monitor_interval_seconds, 60, 3600)
    || settings.monitor_interval_seconds % 60 !== 0) {
    errors.monitor_interval_seconds = "測定間隔を1～60分で入力してください";
  }
  if (!numberInRange(settings.pallet_height_mm, 1, 500)) {
    errors.pallet_height_mm = "パレット高さを1～500mmで入力してください";
  }
  if (!integerInRange(settings.frame_count, 3, 120)) {
    errors.frame_count = "床校正撮影枚数を3～120枚で入力してください";
  }
  if (!integerInRange(settings.measurement_frame_count, 1, 120)) {
    errors.measurement_frame_count = "正式測定撮影枚数を1～120枚で入力してください";
  }
  if (!integerInRange(settings.measurement_concurrency, 1, 100)) {
    errors.measurement_concurrency = "同時測定カメラ数を1～100台で入力してください";
  }
  if (!integerInRange(settings.warmup_frames, 0, 60)) {
    errors.warmup_frames = "ウォームアップ枚数を0～60枚で入力してください";
  }
  if (!numberInRange(settings.grid_mm, 2, 50)) {
    errors.grid_mm = "高さグリッドを2～50mmで入力してください";
  }
  if (!numberInRange(settings.occupied_height_mm, 1, Number.POSITIVE_INFINITY)) {
    errors.occupied_height_mm = "箱と判定する最低高さを1mm以上で入力してください";
  }
  return errors;
}

function integerInRange(value: number, min: number, max: number): boolean {
  return Number.isInteger(value) && value >= min && value <= max;
}

function numberInRange(value: number, min: number, max: number): boolean {
  return Number.isFinite(value) && value >= min && value <= max;
}
