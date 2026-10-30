/** Exact compare identities.

 * Repeated query keys are exact names, so a comma stays inside the
 * name. A single key is a legacy comma-delimited link: split the raw
 * text on unencoded commas, then decode each piece. Surrounding
 * whitespace is removed when reading. At most four names, first-seen
 * order.
 */
export function compareSelectionNames(search: string, param: string): string[] {
  const query = search.startsWith("?") ? search.slice(1) : search;
  const repeated = new URLSearchParams(query).getAll(param)
    .map((value) => value.trim())
    .filter(Boolean);
  const parts = repeated.length > 1 ? repeated : legacyNames(query, param);
  const seen = new Set<string>();
  const out: string[] = [];
  for (const name of parts) {
    if (seen.has(name)) continue;
    seen.add(name);
    out.push(name);
    if (out.length === 4) break;
  }
  return out;
}

function legacyNames(query: string, param: string): string[] {
  const raw = rawQueryValue(query, param);
  if (!raw) return [];
  return raw.split(",").map((part) => decodeQueryPart(part).trim()).filter(Boolean);
}

function rawQueryValue(query: string, param: string): string | null {
  for (const piece of query.split("&")) {
    if (!piece) continue;
    const eq = piece.indexOf("=");
    const rawKey = eq === -1 ? piece : piece.slice(0, eq);
    if (decodeQueryPart(rawKey) !== param) continue;
    return eq === -1 ? "" : piece.slice(eq + 1);
  }
  return null;
}

function decodeQueryPart(part: string): string {
  try {
    return decodeURIComponent(part.replace(/\+/g, " "));
  } catch {
    return part;
  }
}

/** One query key per name. Names are not joined on commas. */
export function compareSelectionQuery(mode: string, param: string, names: string[]): string {
  const params = new URLSearchParams();
  params.set("mode", mode);
  for (const name of names) params.append(param, name);
  return params.toString();
}
