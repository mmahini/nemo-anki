import type { AuthTokens, StoredAuth } from "./types";

// Mirrors the web app's localStorage key/shape (frontend/src/auth/AuthContext.tsx)
// so the two clients are easy to reason about together, even though tokens are
// stored separately per origin (an extension page can't read the web app's
// localStorage, and vice versa).
const STORAGE_KEY = "nemo-anki.auth";

export async function loadStoredAuth(): Promise<StoredAuth | null> {
  const result = await chrome.storage.local.get(STORAGE_KEY);
  return (result[STORAGE_KEY] as StoredAuth | undefined) ?? null;
}

export async function saveStoredAuth(payload: StoredAuth): Promise<void> {
  await chrome.storage.local.set({ [STORAGE_KEY]: payload });
}

export async function clearStoredAuth(): Promise<void> {
  await chrome.storage.local.remove(STORAGE_KEY);
}

export async function updateStoredTokens(tokens: AuthTokens): Promise<void> {
  const stored = await loadStoredAuth();
  if (!stored) return;
  await saveStoredAuth({ ...stored, ...tokens });
}
