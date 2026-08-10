import { Link, Navigate } from "react-router-dom";

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
    Icon: IconLayers,
    tone: "der",
    title: "Real Anki flashcards",
    body: "The spaced-repetition engine you trust — faithful SM-2 scheduling, Again / Hard / Good / Easy grading, and cards shown exactly when you're about to forget them. Daily streaks and a heatmap keep the habit visible.",
  },
  {
    Icon: IconSpark,
    tone: "die",
    title: "Turn any chapter into cards",
    body: "Paste a page from Menschen or Oxford Word Skills and the AI reads it, picks the words, sentences and grammar worth learning, and drafts clean cards for you to review before saving.",
  },
  {
    Icon: IconWand,
    tone: "das",
    title: "Cards that fill themselves in",
    body: "One click adds the translation and IPA reading — plus der/die/das articles, plurals and conjugations for German, or collocations and natural examples for English.",
  },
  {
    Icon: IconBook,
    tone: "der",
    title: "Read real books",
    body: "Upload a PDF, split it into lessons, and study straight from the source in either language — with inline translations into your native language whenever you get stuck.",
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
    body: "Chat or speak with an AI partner in German or English, tuned to the vocabulary you're learning, so every exchange reinforces what's in your decks.",
  },
] as const;

export default function LandingPage() {
  const { user } = useAuth();
  const cta = user ? "Go to your decks" : "Start studying";

  // Installed PWA: skip the marketing page and go straight into the app
  // (ProtectedRoute lands signed-out users on sign-in). New installs open at
  // /app via the manifest's start_url; this covers installs that predate it.
  const standalone =
    window.matchMedia("(display-mode: standalone)").matches ||
    (navigator as { standalone?: boolean }).standalone === true;
  if (standalone) return <Navigate to="/app" replace />;

  return (
    <main className="landing">
      <nav className="landing__nav">
        <span className="landing__brand">Nemo&nbsp;Anki</span>
        <div className="landing__navlinks">
          <a href="#features" className="landing__navlink">Features</a>
          <a href="#ai" className="landing__navlink">How it works</a>
          <a href="#about" className="landing__navlink">About</a>
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
            An AI tutor wrapped around real Anki flashcards. Turn coursebooks and
            texts into rich cards in seconds, then read, write and talk your way
            to fluency — in both German and English.
          </p>
          <div className="hero__langs">
            <span className="langpill"><span className="flag flag--de">DE</span> German · Menschen</span>
            <span className="langpill"><span className="flag flag--en">EN</span> English · Oxford Word Skills</span>
          </div>
          <div className="hero__cta">
            <Link to="/app" className="btn btn--primary btn--lg">{cta}</Link>
            <a href="#features" className="btn btn--glass btn--lg">See what it does</a>
          </div>

          {/* An actual Anki-style review card: front, reading, back and grades. */}
          <div className="studycard" aria-hidden>
            <span className="studycard__tag flag--en">English</span>
            <div className="studycard__q">resilient</div>
            <div className="studycard__reading">/rɪˈzɪl.i.ənt/</div>
            <div className="studycard__sep" />
            <div className="studycard__a">able to bounce back quickly from difficulty</div>
            <div className="studycard__grades">
              <span className="grade grade--again">Again</span>
              <span className="grade grade--hard">Hard</span>
              <span className="grade grade--good">Good</span>
              <span className="grade grade--easy">Easy</span>
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
            Drop in text from any lesson, in German or English. The AI extracts
            what matters, detects each card type, and returns structured cards
            with readings, articles and examples already filled in. You stay in
            control: review, edit, and keep only the cards you want.
          </p>
          <Link to="/app" className="btn btn--primary btn--lg">Try it on your own text</Link>
        </div>

        <div className="aidemo__panel" aria-hidden>
          <div className="aidemo__col aidemo__col--in">
            <span className="aidemo__label">Pasted text</span>
            <p className="aidemo__text">
              Ich <mark>gehe</mark> jeden Morgen zur <mark>Arbeit</mark>.
            </p>
            <p className="aidemo__text">
              She stayed calm and <mark>resilient</mark> under real
              <mark> pressure</mark>.
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
              <span className="gcard__pill gcard__pill--verb">verb</span>
              <span className="gcard__front">gehen</span>
              <span className="gcard__back">to go · ich gehe, du gehst…</span>
            </div>
            <div className="gcard">
              <span className="gcard__pill gcard__pill--en">EN</span>
              <span className="gcard__front">resilient</span>
              <span className="gcard__back">able to recover quickly · under pressure</span>
            </div>
          </div>
        </div>
      </section>

      {/* ---------- TUNED TO EACH LANGUAGE ---------- */}
      <section className="langs">
        <header className="section-head">
          <span className="section-kicker">German &amp; English</span>
          <h2>Tuned to the language you're learning</h2>
          <p>
            The same deck, adapted to how each language actually works — so the
            cues that help you remember are always the right ones.
          </p>
        </header>

        <div className="langs__grid">
          <article className="langpanel">
            <h3 className="langpanel__title">
              <span className="flag flag--de">DE</span> German · Menschen
            </h3>
            <p className="langpanel__lede">
              Every noun is tinted by its article, so gender sticks visually long
              before you can recite the rule.
            </p>
            <div className="langpanel__chips">
              <span className="pill--der">der</span>
              <span className="pill--die">die</span>
              <span className="pill--das">das</span>
              <span className="pill--plural">die&nbsp;(pl)</span>
            </div>
            <ul className="langpanel__list">
              <li>Automatic plural forms &amp; full verb conjugations</li>
              <li>Case-aware example sentences</li>
            </ul>
          </article>

          <article className="langpanel">
            <h3 className="langpanel__title">
              <span className="flag flag--en">EN</span> English · Oxford Word Skills
            </h3>
            <p className="langpanel__lede">
              Cards built the way vocabulary is really used — meaning, the words
              it pairs with, and how it sounds.
            </p>
            <div className="langpanel__chips">
              <span className="pill--das">definition</span>
              <span className="pill--der">collocations</span>
              <span className="pill--plural">IPA</span>
            </div>
            <ul className="langpanel__list">
              <li>Natural example sentences for every entry</li>
              <li>Reverse cards to test recall both ways</li>
            </ul>
          </article>
        </div>
      </section>

      {/* ---------- ABOUT ---------- */}
      <section className="about" id="about">
        <header className="section-head">
          <span className="section-kicker">About us</span>
          <h2>Why we built Nemo Anki</h2>
          <p>
            Most language apps cover one slice of learning — flashcards, or reading,
            or conversation. We felt a genuinely complete tool was possible: one that
            supports every side of learning a language, in the same place.
          </p>
        </header>

        <div className="about__grid">
          <article className="teamcard">
            <span className="teamcard__avatar">AY</span>
            <h3 className="teamcard__name">Amene Yazdian</h3>
            <p className="teamcard__role">AI builder &amp; creator of Nemo Anki</p>
            <div className="teamcard__bio">
              <p>
                I'm a Front-End Developer with React and JavaScript at the core of my
                expertise. However, over the past few months, my journey has expanded
                beyond front-end development, and I've become an <strong>AI Builder</strong>{" "}
                — someone who can take an idea from UI design and development all the
                way to the backend, product logic, and AI-powered features.
              </p>
              <p>
                This transition wasn't just about learning a few new technologies; it
                completely changed the way I think about building products. Today, I can
                take an idea from scratch, design its architecture, develop its
                different components, and ultimately turn it into a real, usable
                product.
              </p>
              <p>
                The idea for <strong>Nemo Anki</strong> came directly from this journey.
              </p>
              <p>
                For a long time, while using different language-learning apps, I kept
                running into the same problem: each app was good at one particular area,
                but often lacked the others. One was great for flashcards, another
                focused on reading, some prioritized speaking, while others focused on
                writing. But there were very few tools that brought all of these
                elements together into one cohesive experience that could support the
                entire language-learning process.
              </p>
              <p>
                That's why I built <strong>Nemo Anki</strong> — a platform designed to
                bring flashcards, reading, writing, and speaking together in one place,
                rather than focusing on just one aspect of language learning. The goal
                is to create a more complete learning experience that supports the user
                throughout the entire process of learning a language.
              </p>
            </div>
          </article>

          <article className="teamcard">
            <span className="teamcard__avatar">SS</span>
            <h3 className="teamcard__name">Sahar Salehi</h3>
            <p className="teamcard__role">Backend developer &amp; AI enthusiast</p>
            <div className="teamcard__bio">
              <p>
                I am passionate about programming, artificial intelligence, and backend
                development. I am currently pursuing my learning journey with a focus on
                Python, Java, and AI-related concepts, while developing a strong
                interest in building reliable and efficient backend systems.
              </p>
              <p>
                Curiosity, problem-solving, and continuous learning are very important
                to me. My goal is to strengthen my programming and backend development
                skills, deepen my understanding of artificial intelligence, and
                gradually grow from a learner into someone capable of building
                real-world, practical, and meaningful projects.
              </p>
            </div>
          </article>
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
        German (Menschen) · English (Oxford Word Skills) · faithful SM-2 · works offline (PWA)
      </footer>
    </main>
  );
}
