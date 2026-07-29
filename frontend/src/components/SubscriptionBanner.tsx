import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useAuth } from "../auth/AuthContext";
import { fetchSubscription, type SubscriptionSummary } from "../auth/api";

/** Top-of-page status: trial / active(tier) / expired (+ days left) or a
 * "payment under review" note, plus today's AI usage. Refetches on navigation
 * so the usage count stays current after AI actions. */
export default function SubscriptionBanner() {
  const { user } = useAuth();
  const { t } = useTranslation();
  const location = useLocation();
  const [sub, setSub] = useState<SubscriptionSummary | null>(user?.subscription ?? null);

  useEffect(() => {
    fetchSubscription().then(setSub).catch(() => {});
  }, [location.pathname]);

  if (!sub) return null;

  const tone = sub.pending ? "pending" : sub.state;
  const tierLabel = sub.tier === "pro" ? t("subscription.tierPro") : t("subscription.tierBasic");
  const message = sub.pending
    ? t("subscription.pendingBanner")
    : sub.state === "active"
      ? t("subscription.activeTier", { tier: tierLabel, days: sub.days_left })
      : sub.state === "trial"
        ? t("subscription.trial", { days: sub.days_left })
        : t("subscription.expired");

  const usage =
    sub.ai_limit != null ? t("subscription.usage", { used: sub.ai_used, limit: sub.ai_limit }) : null;

  return (
    <div className={`subbanner subbanner--${tone}`}>
      <span className="subbanner__msg">{message}</span>
      {usage && <span className="subbanner__usage">{usage}</span>}
      {!sub.pending && (
        <Link to="/app/subscribe" className="subbanner__cta">
          {sub.state === "active" ? t("subscription.renew") : t("subscription.subscribe")}
        </Link>
      )}
    </div>
  );
}
