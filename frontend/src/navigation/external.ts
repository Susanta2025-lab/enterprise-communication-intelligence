export function isSafeAuthorizationUrl(value: string): boolean {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    return false;
  }
  if (parsed.protocol !== "https:") {
    return false;
  }
  if (parsed.username || parsed.password) {
    return false;
  }
  return Boolean(parsed.hostname);
}

export function assignBrowserLocation(url: string): void {
  window.location.assign(url);
}

export function navigateToAuthorizationUrl(url: string): boolean {
  if (!isSafeAuthorizationUrl(url)) {
    return false;
  }
  assignBrowserLocation(url);
  return true;
}
