import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

export default function ProtectedRoute() {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <main className="auth">
        <div className="auth__card">Loading…</div>
      </main>
    );
  }
  if (!user) {
    return <Navigate to="/auth/sign-in" replace state={{ from: location }} />;
  }
  return <Outlet />;
}
