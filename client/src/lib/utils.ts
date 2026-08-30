import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Human label for a FIR. Prefer the real crime/case number; only fall back to
 * the internal id, and shorten it if it's a bare UUID so the UI never shows a
 * `a162ad7c-…` wall.
 */
export function firLabel(
  crimeNo?: string | null,
  firId?: string | null,
  fallback = 'Unlinked FIR',
): string {
  const cn = String(crimeNo ?? '').trim();
  if (cn) return `FIR ${cn}`;
  const id = String(firId ?? '').trim();
  if (!id) return fallback;
  return UUID_RE.test(id) ? `FIR ${id.slice(0, 8).toUpperCase()}` : id;
}

// The Catalyst AppSail backend occasionally resets the connection --
// observed as a raw "TypeError: Failed to fetch" (not an HTTP error
// response) across multiple endpoints (query, transcribe, hypothesis). A
// single retry papers over these transient blips instead of surfacing an
// error on the first hiccup.
export async function fetchWithRetry(url: string, options: RequestInit, retries = 1): Promise<Response> {
  try {
    return await fetch(url, options);
  } catch (err) {
    if (retries > 0 && err instanceof TypeError) {
      await new Promise(r => setTimeout(r, 800));
      return fetchWithRetry(url, options, retries - 1);
    }
    throw err;
  }
}
