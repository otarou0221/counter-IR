export function artifactUrl(path: string): string {
  return `/artifacts/${path.split("/").map(encodeURIComponent).join("/")}`;
}

