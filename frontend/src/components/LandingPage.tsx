import { Link } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

export default function LandingPage() {
  const { user } = useAuth();
  return (
    <main className="landing">
      <nav className="landing__nav">
        <span className="landing__brand">Nemo&nbsp;Anki</span>
        <Link to={user ? "/app" : "/auth/sign-in"} className="btn btn--ghost">
          {user ? "Open app" : "Sign in"}
        </Link>
      </nav>

      <section className="landing__hero">
        <h1>
          Learn words that <span className="accent">stick</span>.
        </h1>
        <p className="landing__lede">
          Spaced-repetition flashcards with Anki's proven scheduling — built for
          German (Menschen) and English (Oxford Word Skills). Vocab, sentences and
          grammar, with readings and article colours that make sense.
        </p>
        <div className="landing__cta">
          <Link to={user ? "/app" : "/auth/sign-in"} className="btn btn--primary btn--lg">
            {user ? "Go to your decks" : "Start studying"}
          </Link>
        </div>

        <div className="landing__cards">
          <div className="mini-card mini-card--der">
            <span className="mini-card__pill pill--der">der</span>
            <span className="mini-card__word art-der">Name</span>
          </div>
          <div className="mini-card mini-card--die">
            <span className="mini-card__pill pill--die">die</span>
            <span className="mini-card__word art-die">Frau</span>
          </div>
          <div className="mini-card mini-card--das">
            <span className="mini-card__pill pill--das">das</span>
            <span className="mini-card__word art-das">Kind</span>
          </div>
        </div>
      </section>

      <footer className="landing__footer">
        Faithful SM-2 scheduling · der=blue · die=red · das=green
      </footer>
    </main>
  );
}
