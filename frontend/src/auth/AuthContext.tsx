import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { AuthTokens, AuthUser } from "./api";
import {
  configureAuth,
  fetchMe,
  refreshAccessToken,
  NetworkError,
  ServerError,
} from "./api";
import { cdpIdentify, cdpReset, cdpTrack } from "../lib/cdp-pixel";
import { applyLanguage } from "../i18n";

const STORAGE_KEY = "nemo-anki.auth";
const PROACTIVE_REFRESH_MS = 10 * 60 * 1000;

type StoredAuth = AuthTokens & { user: AuthUser };

type AuthContextValue = {
  user: AuthUser | null;
  isLoading: boolean;
  signIn: (payload: StoredAuth, opts?: { isNewUser?: boolean }) => void;
  signOut: () => void;
  refreshUser: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function loadStored(): StoredAuth | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredAuth) : null;
  } catch {
    return null;
  }
}

function saveStored(payload: StoredAuth) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setLoading] = useState(true);

  const signOut = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    configureAuth({ tokens: null });
    cdpReset(); // Wiser CDP: clear identity for the next user on this device
    setUser(null);
  }, []);

  const signIn = useCallback(
    (payload: StoredAuth, opts?: { isNewUser?: boolean }) => {
      saveStored(payload);
      configureAuth({
        tokens: { access: payload.access, refresh: payload.refresh },
        onTokensChange: (updated) => {
          saveStored({ ...updated, user: payload.user });
        },
        onAuthFailed: () => signOut(),
      });
      setUser(payload.user);
      // Wiser CDP: a first-ever verification is a one-time `signup`; every explicit
      // OTP sign-in (first or returning) is also a `login`. identify is handled by
      // the user effect below, covering both sign-in and session restore.
      if (opts?.isNewUser) cdpTrack("signup");
      cdpTrack("login");
    },
    [signOut],
  );

  const refreshUser = useCallback(async () => {
    const fresh = await fetchMe();
    setUser(fresh);
    const stored = loadStored();
    if (stored) saveStored({ ...stored, user: fresh });
  }, []);

  useEffect(() => {
    const stored = loadStored();
    if (!stored) {
      setLoading(false);
      return;
    }
    configureAuth({
      tokens: { access: stored.access, refresh: stored.refresh },
      onTokensChange: (updated) => saveStored({ ...updated, user: stored.user }),
      onAuthFailed: () => signOut(),
    });

    let cancelled = false;
    (async () => {
      try {
        const fresh = await fetchMe();
        if (!cancelled) {
          setUser(fresh);
          saveStored({ access: stored.access, refresh: stored.refresh, user: fresh });
        }
      } catch (err) {
        if (cancelled) return;
        if (err instanceof NetworkError || err instanceof ServerError) {
          setUser(stored.user);
          setLoading(false);
          return;
        }
        try {
          const newAccess = await refreshAccessToken();
          if (!newAccess) {
            signOut();
            return;
          }
          const fresh = await fetchMe();
          if (!cancelled) {
            setUser(fresh);
            saveStored({ access: newAccess, refresh: stored.refresh, user: fresh });
          }
        } catch (refreshErr) {
          if (cancelled) return;
          if (refreshErr instanceof NetworkError || refreshErr instanceof ServerError) {
            setUser(stored.user);
            setLoading(false);
            return;
          }
          signOut();
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Apply saved UI language whenever the user object changes (login or session restore).
  useEffect(() => {
    if (!user) return;
    applyLanguage(user.ui_language ?? "en");
  }, [user]);

  // Wiser CDP: attach the signed-in user to events whenever it becomes available
  // (sign-in or restored session), so every event folds into one profile.
  useEffect(() => {
    if (!user) return;
    cdpIdentify({ external_id: String(user.id), email: user.email, name: user.display_name });
  }, [user]);

  useEffect(() => {
    if (!user) return;
    const id = window.setInterval(() => {
      refreshAccessToken().catch(() => {});
    }, PROACTIVE_REFRESH_MS);
    return () => window.clearInterval(id);
  }, [user]);

  const value = useMemo<AuthContextValue>(
    () => ({ user, isLoading, signIn, signOut, refreshUser }),
    [user, isLoading, signIn, signOut, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
