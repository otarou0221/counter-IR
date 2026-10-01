import type { DebugCatalog, SavedCapture } from "./types";

export const DEBUG_CAPTURE_PAGE_SIZE = 50;

function capturedAtLabel(capture: SavedCapture): string {
  return new Date(capture.captured_at).toLocaleString("ja-JP");
}

export function floorCaptureLabel(capture: SavedCapture): string {
  return `${capturedAtLabel(capture)} / ${capture.capture_id}`;
}

export function currentCaptureLabel(capture: SavedCapture): string {
  const source = capture.retention === "transient" ? "通常監視" : "診断撮影";
  return `【${source}】${capturedAtLabel(capture)} / ${capture.capture_id}`;
}

export function appendDebugCatalogPage(
  current: DebugCatalog,
  incoming: DebugCatalog,
): DebugCatalog {
  const knownIds = new Set(current.current_captures.map((capture) => capture.capture_id));
  return {
    ...incoming,
    current_captures: [
      ...current.current_captures,
      ...incoming.current_captures.filter((capture) => !knownIds.has(capture.capture_id)),
    ],
  };
}
