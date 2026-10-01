import { useCallback, useEffect, useState } from "react";
import { ResourceCache } from "./resourceCache";

const imageCache = new ResourceCache<HTMLImageElement>(4);

export type CachedImageState = {
  image: HTMLImageElement | null;
  status: "loading" | "ready" | "error";
  error: Error | null;
  retry: () => void;
};

type InternalState = Omit<CachedImageState, "retry"> & { url: string };

function initialState(url: string): InternalState {
  const cached = imageCache.peek(url);
  return cached
    ? { url, image: cached, status: "ready", error: null }
    : { url, image: null, status: "loading", error: null };
}

function retryUrl(url: string, attempt: number): string {
  if (attempt === 0) return url;
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}image_retry=${attempt}`;
}

export function useCachedImage(url: string, timeoutMs = 10_000): CachedImageState {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<InternalState>(() => initialState(url));
  const currentState = state.url === url ? state : initialState(url);

  useEffect(() => {
    const cached = imageCache.get(url);
    if (cached) {
      setState({ url, image: cached, status: "ready", error: null });
      return;
    }

    let active = true;
    let timer: number | undefined;
    const image = new window.Image();
    setState({ url, image: null, status: "loading", error: null });

    const clearPendingWork = () => {
      if (timer !== undefined) window.clearTimeout(timer);
      image.onload = null;
      image.onerror = null;
    };
    const fail = (error: Error) => {
      clearPendingWork();
      if (!active) return;
      image.src = "";
      setState({ url, image: null, status: "error", error });
    };
    const complete = () => {
      clearPendingWork();
      if (!active) return;
      if (image.naturalWidth < 1 || image.naturalHeight < 1) {
        fail(new Error("画像データを表示できません"));
        return;
      }
      imageCache.set(url, image);
      setState({ url, image, status: "ready", error: null });
    };

    image.onload = complete;
    image.onerror = () => fail(new Error("画像を取得できませんでした"));
    timer = window.setTimeout(() => {
      fail(new Error(`${Math.ceil(timeoutMs / 1000)}秒以内に画像を取得できませんでした`));
    }, timeoutMs);
    image.src = retryUrl(url, attempt);
    if (image.complete) complete();

    return () => {
      active = false;
      clearPendingWork();
      if (!image.complete) image.src = "";
    };
  }, [attempt, timeoutMs, url]);

  const retry = useCallback(() => {
    imageCache.delete(url);
    setAttempt((current) => current + 1);
  }, [url]);

  return { ...currentState, retry };
}
