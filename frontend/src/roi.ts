export type NormalizedRoi = [number, number, number, number];

export type NormalizedPoint = {
  x: number;
  y: number;
};

const clamp01 = (value: number) => Math.min(1, Math.max(0, value));
const roundCoordinate = (value: number) => Number(clamp01(value).toFixed(6));

export function roiFromDrag(
  start: NormalizedPoint,
  end: NormalizedPoint,
  minimumSpan = 0.005,
): NormalizedRoi | null {
  const left = clamp01(Math.min(start.x, end.x));
  const top = clamp01(Math.min(start.y, end.y));
  const right = clamp01(Math.max(start.x, end.x));
  const bottom = clamp01(Math.max(start.y, end.y));

  if (right - left < minimumSpan || bottom - top < minimumSpan) return null;
  return [left, top, right, bottom].map(roundCoordinate) as NormalizedRoi;
}
