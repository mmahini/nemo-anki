import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useAuth } from "../auth/AuthContext";

export default function ProtectedRoute() {
  const { t } = useTranslation();
  const { user, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <main className="auth">
        <div className="auth__card">{t("common.loading")}</div>
      </main>
    );
  }
  if (!user) {
    return <Navigate to="/auth/sign-in" replace state={{ from: location }} />;
  }
  // A fresh account goes through the welcome flow before anything else — it's
  // where the UI language and name get set, so the app has nothing sensible to
  // show until it's done. /welcome itself stays reachable afterwards so the
  // account menu can replay it.
  if (!user.onboarded && location.pathname !== "/welcome") {
    return <Navigate to="/welcome" replace />;
  }
  return <Outlet />;
}
