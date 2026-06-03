import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

export default function AppShell() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="shell">
      <header className="shell__bar">
        <Link to="/app" className="shell__brand">Nemo&nbsp;Anki</Link>
        <nav className="shell__nav">
          <NavLink to="/app" end className="shell__link">Decks</NavLink>
          <NavLink to="/app/books" className="shell__link">Books</NavLink>
          <NavLink to="/app/import" className="shell__link">Import</NavLink>
        </nav>
        <div className="shell__user">
          <span className="shell__email">{user?.email}</span>
          <button
            className="btn btn--ghost btn--sm"
            onClick={() => {
              signOut();
              navigate("/");
            }}
          >
            Sign out
          </button>
        </div>
      </header>
      <main className="shell__main">
        <Outlet />
      </main>
    </div>
  );
}
