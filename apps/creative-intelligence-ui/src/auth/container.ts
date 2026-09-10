const KEY = "ci-container-id";

function fresh(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `c-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e9).toString(36)}`;
}

let memoryFallback = "";

function load(): string {
  try {
    return window.localStorage.getItem(KEY) ?? "";
  } catch {
    return memoryFallback;
  }
}

function save(id: string): void {
  try {
    window.localStorage.setItem(KEY, id);
  } catch {
    memoryFallback = id;
  }
}

/** Stable installation/account container id (item 18). One browser profile
 *  keeps one id; the server binds sessions to it so the account switcher
 *  can never see another installation's accounts. */
export function installationContainer(): string {
  const existing = load();
  if (existing && /^[\w-]{1,64}$/.test(existing)) return existing;
  const id = fresh();
  save(id);
  return id;
}
