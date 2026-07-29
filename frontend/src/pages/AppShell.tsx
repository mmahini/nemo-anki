import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useAuth } from "../auth/AuthContext";
import { updateMe } from "../auth/api";
import { applyLanguage } from "../i18n";
import SubscriptionBanner from "../components/SubscriptionBanner";

export default function AppShell() {
  const { user, signOut, refreshUser } = useAuth();
  const navigate = useNavigate();
  const { t } = useTranslation();

  async function toggleLanguage() {
    const next = user?.ui_language === "fa" ? "en" : "fa";
    applyLanguage(next);
    try {
      await updateMe({ ui_language: next });
    } catch {
      applyLanguage(user?.ui_language ?? "en");
      return;
    }
    refreshUser().catch(() => {});
  }

  return (
    <div className="shell">
      <header className="shell__bar">
        <Link to="/app" className="shell__brand">Nemo&nbsp;Anki</Link>
        <nav className="shell__nav">
          <NavLink to="/app" end className="shell__link">{t("nav.decks")}</NavLink>
          <NavLink to="/app/books" className="shell__link">{t("nav.books")}</NavLink>
          <NavLink to="/app/import" className="shell__link">{t("nav.import")}</NavLink>
          <NavLink to="/app/write" className="shell__link">{t("nav.writing")}</NavLink>
          <NavLink to="/app/conversation" className="shell__link">{t("nav.conversation")}</NavLink>
        </nav>
        <div className="shell__user">
          <span className="shell__email">{user?.email}</span>
          <button
            className="btn btn--ghost btn--sm"
            onClick={toggleLanguage}
            title={user?.ui_language === "fa" ? "Switch to English" : "تغییر به فارسی"}
          >
            {user?.ui_language === "fa" ? "EN" : "فا"}
          </button>
          <button
            className="btn btn--ghost btn--sm"
            onClick={() => {
              signOut();
              navigate("/");
            }}
          >
            {t("nav.signOut")}
          </button>
        </div>
      </header>
      <SubscriptionBanner />
      <main className="shell__main">
        <Outlet />
      </main>
    </div>
  );
}
