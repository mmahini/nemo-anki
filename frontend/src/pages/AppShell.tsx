import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import InviteButton from "../components/InviteButton";
import SubscriptionBanner from "../components/SubscriptionBanner";
import UserMenu from "../components/UserMenu";
import { SubscriptionProvider, useSubscription } from "../subscription/SubscriptionContext";

/* Small inline nav icons for the mobile bottom bar. */
function IconHome() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M4 10.5L12 4l8 6.5V20a1 1 0 01-1 1h-5v-6h-4v6H5a1 1 0 01-1-1v-9.5z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
    </svg>
  );
}
function IconDecks() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M12 3l9 5-9 5-9-5 9-5z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="M3 13l9 5 9-5" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" opacity=".6" />
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
function IconReels() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect x="3" y="4" width="18" height="16" rx="3" stroke="currentColor" strokeWidth="2" />
      <path d="M3 9h18M9 4l3 5M15 4l3 5" stroke="currentColor" strokeWidth="2" opacity=".6" />
      <path d="M11 12.5l4 2.2-4 2.3v-4.5z" fill="currentColor" />
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

/* Home carries the daily dashboard plus the Books/Import doorways, so neither
   needs a nav slot; Support lives in the account menu, and Writing +
   Conversation merged into Practice. Quiz (the placement test) is its own
   destination — a full-screen flow, not a Practice tab.

   Five tabs is the ceiling on a phone: the labels are already short, and a
   sixth would either wrap or force scrolling. Anything added after Reels has
   to displace something, not squeeze in beside it. */
const NAV = [
  { to: "/app", end: true, key: "nav.home", Icon: IconHome },
  { to: "/app/decks", end: false, key: "nav.decks", Icon: IconDecks },
  { to: "/app/practice", end: false, key: "nav.practice", Icon: IconPractice },
  { to: "/app/reels", end: false, key: "nav.reels", Icon: IconReels },
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

/* The five top-level destinations. Only these show the mobile bottom tab bar;
   anything deeper (deck cards, a book, import, support…) is a sub-page that
   hides the bar and offers its own back button instead. Practice keeps the bar
   across its tabs — they're a segmented control, not deeper navigation. */
const MAIN_ROUTES = [
  /^\/app\/?$/,
  /^\/app\/decks\/?$/,
  /^\/app\/practice(\/[\w-]+)?\/?$/,
  /^\/app\/reels\/?$/,
  /^\/app\/placement-test\/?$/,
];

export default function AppShell() {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const isMain = MAIN_ROUTES.some((re) => re.test(pathname));
  // Reels is an immersive full-bleed feed: the shell drops its gutters and
  // pins its height so the feed can snap one-reel-per-screen.
  const isReels = /^\/app\/reels\/?$/.test(pathname);

  return (
    <SubscriptionProvider>
      <div className={`shell${isMain ? "" : " shell--subpage"}${isReels ? " shell--reels" : ""}`}>
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
            <InviteButton />
            <UserMenu />
          </div>
        </header>

        <SubscriptionBanner />

        <main className="shell__main">
          <Outlet />
        </main>

        {/* Mobile bottom tab bar (hidden on desktop via CSS) — main pages only. */}
        {isMain && (
          <nav className="shell__tabbar">
            {NAV.map(({ to, end, key, Icon }) => (
              <NavLink key={to} to={to} end={end} className="tabbar__link">
                <span className="tabbar__icon"><Icon /></span>
                <span className="tabbar__label">{t(key)}</span>
              </NavLink>
            ))}
          </nav>
        )}
      </div>
    </SubscriptionProvider>
  );
}
