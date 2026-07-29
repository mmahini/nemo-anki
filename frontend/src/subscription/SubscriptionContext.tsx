import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { fetchSubscription, type SubscriptionSummary } from "../auth/api";

type Ctx = { sub: SubscriptionSummary | null; refresh: () => void };

const SubscriptionCtx = createContext<Ctx>({ sub: null, refresh: () => {} });

/** Single source of subscription status + AI usage for the app chrome (header
 * usage chip, status banner, user menu). Refetches on navigation so usage stays
 * current after AI actions. */
export function SubscriptionProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const location = useLocation();
  const [sub, setSub] = useState<SubscriptionSummary | null>(user?.subscription ?? null);

  const refresh = useCallback(() => {
    fetchSubscription()
      .then(setSub)
      .catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
  }, [location.pathname, refresh]);

  return <SubscriptionCtx.Provider value={{ sub, refresh }}>{children}</SubscriptionCtx.Provider>;
}

export function useSubscription(): Ctx {
  return useContext(SubscriptionCtx);
}
