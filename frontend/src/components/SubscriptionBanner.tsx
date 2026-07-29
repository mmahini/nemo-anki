import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useSubscription } from "../subscription/SubscriptionContext";

/** A nudge bar shown only when the user should act: on trial, expired, or with a
 * payment under review. Active (paid) subscribers see their status in the user
 * menu instead — no bar. AI usage lives in the header (see AppShell). */
export default function SubscriptionBanner() {
  const { sub } = useSubscription();
  const { t } = useTranslation();

  if (!sub || sub.state === "active") return null;

  const tone = sub.pending ? "pending" : sub.state;
  const message = sub.pending
    ? t("subscription.pendingBanner")
    : sub.state === "trial"
      ? t("subscription.trial", { days: sub.days_left })
      : t("subscription.expired");

  return (
    <div className={`subbanner subbanner--${tone}`}>
      <span className="subbanner__msg">{message}</span>
      {!sub.pending && (
        <Link to="/app/subscribe" className="subbanner__cta">
          {t("subscription.subscribe")}
        </Link>
      )}
    </div>
  );
}
