import { Link } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

/* Inline SVG illustrations — kept in-file so the landing stays a single
   self-contained unit that works offline (PWA) with no external assets. */

function IconSpark() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 2.5l1.9 5.2 5.2 1.9-5.2 1.9L12 16.7l-1.9-5.2L4.9 9.6l5.2-1.9L12 2.5z"
        fill="currentColor"
      />
      <circle cx="18.5" cy="17.5" r="1.7" fill="currentColor" opacity=".6" />
      <circle cx="5.5" cy="18" r="1.1" fill="currentColor" opacity=".45" />
    </svg>
  );
}
function IconWand() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M4 20l9-9" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
      <path
        d="M15 4l.9 2.1L18 7l-2.1.9L15 10l-.9-2.1L12 7l2.1-.9L15 4z"
        fill="currentColor"
      />
      <path d="M19.5 12.5l.6 1.4 1.4.6-1.4.6-.6 1.4-.6-1.4-1.4-.6 1.4-.6.6-1.4z" fill="currentColor" opacity=".7" />
    </svg>
  );
}
function IconLayers() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M12 3l9 5-9 5-9-5 9-5z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="M3 13l9 5 9-5" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" opacity=".55" />
    </svg>
  );
}
function IconBook() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 5.5C10.5 4.3 8.4 4 4 4v13c4.4 0 6.5.3 8 1.5 1.5-1.2 3.6-1.5 8-1.5V4c-4.4 0-6.5.3-8 1.5z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <path d="M12 5.5v13" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}
function IconPen() {
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

const FEATURES = [
  {
    Icon: IconSpark,
    tone: "der",
    title: "Turn any chapter into cards",
    body: "Paste a page from your coursebook and the AI reads it, picks the words, sentences and grammar worth learning, and drafts clean cards you can review and tweak before saving.",
  },
  {
    Icon: IconWand,
    tone: "die",
    title: "Cards that fill themselves in",
    body: "One click enriches a term with its translation, IPA reading, the right der/die/das article, plural form and full verb conjugations — no more typing every field by hand.",
  },
  {
    Icon: IconLayers,
    tone: "das",
    title: "Scheduling that actually works",
    body: "Faithful SM-2 spaced repetition shows each card exactly when you're about to forget it. Daily streaks and an activity heatmap keep the habit visible.",
  },
  {
    Icon: IconBook,
    tone: "der",
    title: "Read real books",
    body: "Upload a PDF, split it into lessons, and study straight from the source — with inline translations into your native language whenever you get stuck.",
  },
  {
    Icon: IconPen,
    tone: "die",
    title: "Practise writing",
    body: "Get an AI reference text to translate, write your own version, and receive feedback — turning passive vocabulary into words you can actually produce.",
  },
  {
    Icon: IconChat,
    tone: "das",
    title: "Hold a conversation",
    body: "Chat or speak with an AI partner in your target language, tuned to the vocabulary you're learning, so every exchange reinforces what's in your decks.",
  },
] as const;

export default function LandingPage() {
  const { user } = useAuth();
  const cta = user ? "Go to your decks" : "Start studying";

  return (
    <main className="landing">
      <nav className="landing__nav">
        <span className="landing__brand">Nemo&nbsp;Anki</span>
        <div className="landing__navlinks">
          <a href="#features" className="landing__navlink">Features</a>
          <a href="#ai" className="landing__navlink">How it works</a>
          {/* Always go to /app — ProtectedRoute sends guests to sign-in, so a
              signed-in user is never asked to log in again. */}
          <Link to="/app" className="btn btn--ghost">
            {user ? "Open app" : "Sign in"}
          </Link>
        </div>
      </nav>

      {/* ---------- HERO ---------- */}
      <section className="hero">
        <div className="hero__aurora" aria-hidden>
          <span className="hero__blob hero__blob--1" />
          <span className="hero__blob hero__blob--2" />
          <span className="hero__blob hero__blob--3" />
        </div>

        <div className="hero__inner">
          <span className="hero__badge">
            <IconSpark />
            Powered by Gemini AI
          </span>
          <h1 className="hero__title">
            Learn words that <span className="accent">stick</span>.
          </h1>
          <p className="hero__lede">
            An AI language tutor built on Anki's proven spaced repetition. Turn
            coursebooks and real texts into rich flashcards in seconds — then
            read, write and talk your way to fluency in German and English.
          </p>
          <div className="hero__cta">
            <Link to="/app" className="btn btn--primary btn--lg">{cta}</Link>
            <a href="#features" className="btn btn--glass btn--lg">See what it does</a>
          </div>

          <div className="hero__cards">
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
        </div>
      </section>

      {/* ---------- FEATURES ---------- */}
      <section className="features" id="features">
        <header className="section-head">
          <span className="section-kicker">Everything in one place</span>
          <h2>A full toolkit for building real fluency</h2>
          <p>
            Most apps stop at flashcards. Nemo Anki takes you from a blank deck
            to reading, writing and speaking — with AI doing the tedious parts.
          </p>
        </header>

        <div className="features__grid">
          {FEATURES.map(({ Icon, tone, title, body }) => (
            <article className={`feature feature--${tone}`} key={title}>
              <span className="feature__icon"><Icon /></span>
              <h3 className="feature__title">{title}</h3>
              <p className="feature__body">{body}</p>
            </article>
          ))}
        </div>
      </section>

      {/* ---------- AI IN ACTION ---------- */}
      <section className="aidemo" id="ai">
        <div className="aidemo__copy">
          <span className="section-kicker">AI in action</span>
          <h2>From a paragraph to a deck — instantly</h2>
          <p>
            Drop in text from any lesson. The AI extracts what matters, detects
            the card type, and returns structured cards with readings, articles
            and examples already filled in. You stay in control: review, edit,
            and keep only the cards you want.
          </p>
          <Link to="/app" className="btn btn--primary btn--lg">Try it on your own text</Link>
        </div>

        <div className="aidemo__panel" aria-hidden>
          <div className="aidemo__col aidemo__col--in">
            <span className="aidemo__label">Pasted text</span>
            <p className="aidemo__text">
              Ich <mark>gehe</mark> jeden Morgen zur <mark>Arbeit</mark>. Die
              <mark> Wohnung</mark> ist klein aber gemütlich.
            </p>
          </div>
          <div className="aidemo__arrow">
            <IconWand />
          </div>
          <div className="aidemo__col aidemo__col--out">
            <span className="aidemo__label">Generated cards</span>
            <div className="gcard">
              <span className="gcard__pill pill--die">die</span>
              <span className="gcard__front art-die">Arbeit</span>
              <span className="gcard__back">work · ˈaʁbaɪt</span>
            </div>
            <div className="gcard">
              <span className="gcard__pill pill--die">die</span>
              <span className="gcard__front art-die">Wohnung</span>
              <span className="gcard__back">flat, apartment</span>
            </div>
            <div className="gcard">
              <span className="gcard__pill gcard__pill--verb">verb</span>
              <span className="gcard__front">gehen</span>
              <span className="gcard__back">to go · ich gehe, du gehst…</span>
            </div>
          </div>
        </div>
      </section>

      {/* ---------- COLOUR SYSTEM ---------- */}
      <section className="colours">
        <header className="section-head">
          <span className="section-kicker">Built for German</span>
          <h2>See gender before you memorise it</h2>
          <p>
            Every noun is tinted by its article, so the right gender sticks
            visually — long before you can recite the rule.
          </p>
        </header>
        <div className="colours__row">
          <div className="colours__chip"><span className="pill--der">der</span> masculine · blue</div>
          <div className="colours__chip"><span className="pill--die">die</span> feminine · red</div>
          <div className="colours__chip"><span className="pill--das">das</span> neuter · green</div>
          <div className="colours__chip"><span className="pill--plural">die</span> plural · purple</div>
        </div>
      </section>

      {/* ---------- CTA BAND ---------- */}
      <section className="ctaband">
        <div className="ctaband__inner">
          <h2>Ready to make words stick?</h2>
          <p>Free to start. Bring your coursebook — the AI does the busywork.</p>
          <Link to="/app" className="btn btn--primary btn--lg">{cta}</Link>
        </div>
      </section>

      <footer className="landing__footer">
        Faithful SM-2 scheduling · works offline (PWA) · der=blue · die=red · das=green
      </footer>
    </main>
  );
}
