import { useEffect, useState } from "react";
import type { SettingsValidationIssue } from "./settingsValidation";

export function useSettingsIssueNavigation(
  selectedCameraId: string,
  onCameraChange: (cameraId: string) => void,
) {
  const [pendingIssue, setPendingIssue] = useState<SettingsValidationIssue | null>(null);

  useEffect(() => {
    if (!pendingIssue) return;
    if (pendingIssue.cameraId && pendingIssue.cameraId !== selectedCameraId) {
      onCameraChange(pendingIssue.cameraId);
      return;
    }
    const frame = window.requestAnimationFrame(() => {
      const target = document.getElementById(pendingIssue.targetId);
      if (!target) return;
      let disclosure = target.closest("details");
      while (disclosure) {
        disclosure.open = true;
        disclosure = disclosure.parentElement?.closest("details") ?? null;
      }
      target.focus({ preventScroll: true });
      target.scrollIntoView({ behavior: "smooth", block: "center" });
      setPendingIssue(null);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [onCameraChange, pendingIssue, selectedCameraId]);

  return setPendingIssue;
}
