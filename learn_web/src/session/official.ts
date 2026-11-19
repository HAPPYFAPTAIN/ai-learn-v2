/** Reuse the official site's existing login renewal protocol. Never store model keys. */
const ACCESS = "aethericai-community-access-token";
const REFRESH = "aethericai-community-refresh-token";
export async function renewOfficial(owner: string, signal: AbortSignal) {
  const initial = localStorage.getItem(ACCESS);
  if (!initial) return; // Cookie-only API deployments can renew their cookie server-side.
  let token = initial;
  const call = (path: string, body?: unknown, bearer = token) =>
    fetch(`/official-api/api/v1${path}`, {
      method: body === undefined ? "GET" : "POST",
      credentials: "same-origin",
      signal,
      headers: {
        "Content-Type": "application/json",
        ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
  const unchanged = () => localStorage.getItem(ACCESS) === token;
  let profile = await call("/console/me");
  if (profile.status === 401 && localStorage.getItem(REFRESH)) {
    const refreshed = await call(
      "/auth/refresh",
      { refreshToken: localStorage.getItem(REFRESH) },
      "",
    );
    if (!refreshed.ok) throw new Error("登录已过期，请从官网重新进入。");
    const next = await refreshed.json();
    if (!unchanged() || signal.aborted) return;
    localStorage.setItem(ACCESS, next.accessToken);
    localStorage.setItem(REFRESH, next.refreshToken);
    localStorage.setItem(
      "aethericai-community-access-expires",
      String(next.accessTokenExpiresAtEpochMs),
    );
    token = next.accessToken;
    profile = await call("/console/me");
  }
  if (profile.status === 401 || profile.status === 403)
    throw new Error("登录已过期，请从官网重新进入。");
  if (!profile.ok) return;
  if ((await profile.json()).userId !== owner)
    throw new Error("登录账号已变化，请从官网重新进入。");
  if (!unchanged() || signal.aborted) return;
  const response = await call("/console/learn-everything/entry", {});
  if (response.status === 401 || response.status === 403)
    throw new Error("登录或产品资格已过期，请从官网重新进入。");
  if (!response.ok) return;
  const entry = await response.json();
  const url = new URL(entry.url, location.origin);
  if (
    url.origin !== location.origin ||
    url.pathname !== "/official/learn-everything/"
  )
    return;
  if (!unchanged() || signal.aborted) return;
  const accepted = await fetch(url, {
    credentials: "same-origin",
    signal,
    headers: { "X-Learn-Expected-User": owner },
    cache: "no-store",
  });
  if (accepted.status === 409)
    throw new Error("登录账号已变化，请从官网重新进入。");
}
