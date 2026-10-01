export const IPV4_OCTET_COUNT = 4;

export function splitIpv4(value: string): string[] {
  const parts = value.split(".").slice(0, IPV4_OCTET_COUNT);
  return Array.from({ length: IPV4_OCTET_COUNT }, (_, index) => parts[index] ?? "");
}

export function joinIpv4(parts: string[]): string {
  const normalized = Array.from(
    { length: IPV4_OCTET_COUNT },
    (_, index) => parts[index] ?? "",
  );
  return normalized.every((part) => part === "") ? "" : normalized.join(".");
}

export function normalizeIpv4Octet(value: string): string {
  return value.replace(/\D/g, "").slice(0, 3).replace(/^0+(?=\d)/, "");
}

export function ipv4ValidationError(value: string): string | undefined {
  if (!value.trim()) return "接続先IPを入力してください";
  const parts = value.split(".");
  if (parts.length !== IPV4_OCTET_COUNT || parts.some((part) => !/^\d{1,3}$/.test(part))) {
    return "IPv4アドレスを4つの数字で入力してください";
  }
  if (parts.some((part) => Number(part) > 255 || String(Number(part)) !== part)) {
    return "各数字を0〜255で入力してください";
  }
  return undefined;
}

export function isValidIpv4(value: string): boolean {
  return ipv4ValidationError(value) === undefined;
}
