import { Link, NavLink, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";

import SubscriptionBanner from "../components/SubscriptionBanner";
import UserMenu from "../components/UserMenu";
import { SubscriptionProvider, useSubscription } from "../subscription/SubscriptionContext";

/* Small inline nav icons for the mobile bottom bar. */
function IconDecks() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M12 3l9 5-9 5-9-5 9-5z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="M3 13l9 5 9-5" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" opacity=".6" />
    </svg>
  );
}
function IconBooks() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M12 5.5C10.5 4.3 8.4 4 4 4v13c4.4 0 6.5.3 8 1.5 1.5-1.2 3.6-1.5 8-1.5V4c-4.4 0-6.5.3-8 1.5z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="M12 5.5v13" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}
function IconPractice() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M4 20l3.5-.9L18 8.6a2 2 0 000-2.8l-.8-.8a2 2 0 00-2.8 0L3.9 15.5 3 19l1 1z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="M13.5 6.5l4 4" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}
function IconStats() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M4 20V5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M4 20h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M8.5 20v-6M13 20V8.5M17.5 20v-9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
function IconQuiz() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M12 3l9 4.5-9 4.5-9-4.5L12 3z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="M6 10.5V15c0 1.7 2.7 3 6 3s6-1.3 6-3v-4.5" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
    </svg>
  );
}

/* Import moved to a button on the deck list (that's where you already are when
   you want to add cards), Support to the account menu, and Writing +
   Conversation merged into Practice. Quiz (the placement test) is its own
   destination — a full-screen flow, not a Practice tab. */
const NAV = [
  { to: "/app", end: true, key: "nav.decks", Icon: IconDecks },
  { to: "/app/stats", end: false, key: "nav.stats", Icon: IconStats },
  { to: "/app/books", end: false, key: "nav.books", Icon: IconBooks },
  { to: "/app/practice", end: false, key: "nav.practice", Icon: IconPractice },
  { to: "/app/placement-test", end: false, key: "nav.quiz", Icon: IconQuiz },
] as const;

function AiUsageChip() {
  const { sub } = useSubscription();
  const { t } = useTranslation();
  if (!sub) return null;
  const unlimited = sub.ai_limit == null;
  const over = !unlimited && sub.ai_used >= (sub.ai_limit ?? 0);
  return (
    <span className={`shell__usage ${over ? "shell__usage--over" : ""}`} title={t("subscription.usageTitle")}>
      {unlimited
        ? t("subscription.usageUnlimited", { used: sub.ai_used })
        : t("subscription.usage", { used: sub.ai_used, limit: sub.ai_limit })}
    </span>
  );
}

export default function AppShell() {
  const { t } = useTranslation();

  return (
    <SubscriptionProvider>
      <div className="shell">
        <header className="shell__bar">
          <Link to="/app" className="shell__brand">Nemo&nbsp;Anki</Link>
          <nav className="shell__nav">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} className="shell__link">
                {t(n.key)}
              </NavLink>
            ))}
          </nav>
          <div className="shell__account">
            <AiUsageChip />
            <UserMenu />
          </div>
        </header>

        <SubscriptionBanner />

        <main className="shell__main">
          <Outlet />
        </main>

        {/* Mobile bottom tab bar (hidden on desktop via CSS). */}
        <nav className="shell__tabbar">
          {NAV.map(({ to, end, key, Icon }) => (
            <NavLink key={to} to={to} end={end} className="tabbar__link">
              <span className="tabbar__icon"><Icon /></span>
              <span className="tabbar__label">{t(key)}</span>
            </NavLink>
          ))}
        </nav>
      </div>
    </SubscriptionProvider>
  );
}
