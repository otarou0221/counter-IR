import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import {
  appendDebugCatalogPage,
  DEBUG_CAPTURE_PAGE_SIZE,
} from "./debugCaptures";
import type { DebugCatalog } from "./types";
import type { NoticeHandler } from "./uiNotice";

function emptyCatalog(cameraId: string): DebugCatalog {
  return {
    camera_id: cameraId,
    floor_captures: [],
    current_captures: [],
    current_has_more: false,
    current_capture_limit: 0,
  };
}

export function useDebugCaptureCatalog(cameraId: string, onMessage: NoticeHandler) {
  const [catalog, setCatalog] = useState<DebugCatalog>(() => emptyCatalog(cameraId));
  const [loading, setLoading] = useState(false);
  const requestController = useRef<AbortController | null>(null);

  const loadPage = useCallback(async (offset: number, announce: boolean) => {
    if (!cameraId) {
      setCatalog(emptyCatalog(""));
      return null;
    }
    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;
    setLoading(true);
    try {
      const query = new URLSearchParams({
        camera_id: cameraId,
        current_offset: String(offset),
        current_limit: String(DEBUG_CAPTURE_PAGE_SIZE),
      });
      const loaded = await api<DebugCatalog>(`/api/debug/catalog?${query}`, {
        signal: controller.signal,
      });
      setCatalog((current) => offset === 0
        ? loaded
        : appendDebugCatalogPage(current, loaded));
      if (announce) {
        onMessage(
          `${cameraId}の床撮影${loaded.floor_captures.length}件・積載後撮影${loaded.current_captures.length}件を読み込みました`,
          "success",
        );
      }
      return loaded;
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return null;
      onMessage(error instanceof Error ? error.message : String(error), "error");
      return null;
    } finally {
      if (requestController.current === controller) {
        requestController.current = null;
        setLoading(false);
      }
    }
  }, [cameraId, onMessage]);

  const refresh = useCallback(
    (announce = true) => loadPage(0, announce),
    [loadPage],
  );
  const loadMore = useCallback(
    () => loadPage(catalog.current_captures.length, false),
    [catalog.current_captures.length, loadPage],
  );

  useEffect(() => {
    setCatalog(emptyCatalog(cameraId));
    void refresh();
    return () => requestController.current?.abort();
  }, [cameraId, refresh]);

  return { catalog, loading, refresh, loadMore };
}
