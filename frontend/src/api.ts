export async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(apiErrorMessage(body.detail, response.statusText));
  }
  return response.json() as Promise<T>;
}

function apiErrorMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => (
      typeof item === "object" && item !== null && "msg" in item
        ? String(item.msg) : String(item)
    )).join(" / ");
  }
  return fallback;
}
