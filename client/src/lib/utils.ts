import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
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
