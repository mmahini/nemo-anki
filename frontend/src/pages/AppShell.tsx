import { Link, NavLink, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";

import SubscriptionBanner from "../components/SubscriptionBanner";
import UserMenu from "../components/UserMenu";

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
function IconImport() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M12 4v10m0 0l-3.5-3.5M12 14l3.5-3.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M5 18h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
function IconWrite() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M4 20l3.5-.9L18 8.6a2 2 0 000-2.8l-.8-.8a2 2 0 00-2.8 0L3.9 15.5 3 19l1 1z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="M13.5 6.5l4 4" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}
function IconChat() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M4 5.5h16v10H9.5L5 19v-3.5H4v-10z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="M8 9.5h8M8 12.5h5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

const NAV = [
  { to: "/app", end: true, key: "nav.decks", Icon: IconDecks },
  { to: "/app/books", end: false, key: "nav.books", Icon: IconBooks },
  { to: "/app/import", end: false, key: "nav.import", Icon: IconImport },
  { to: "/app/write", end: false, key: "nav.writing", Icon: IconWrite },
  { to: "/app/conversation", end: false, key: "nav.conversation", Icon: IconChat },
] as const;

export default function AppShell() {
  const { t } = useTranslation();

  return (
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
        <UserMenu />
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
  );
}
