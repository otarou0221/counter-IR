export type RemoteResourceStatus = "loading" | "error" | "ready" | "stale";

export function remoteResourceStatus(data: unknown | null, error: string | null): RemoteResourceStatus {
  if (data === null) return error ? "error" : "loading";
  return error ? "stale" : "ready";
}
