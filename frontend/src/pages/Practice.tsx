import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { writingBooks, type WritingBook } from "../auth/api";
import { LANGS } from "./practice/languages";
import ReadPanel from "./practice/ReadPanel";
import SpeakPanel from "./practice/SpeakPanel";
import WritePanel from "./practice/WritePanel";

const TABS = ["write", "speak", "read"] as const;
type Tab = (typeof TABS)[number];

const LANG_KEY = "nemo-anki.practice.lang";

function storedLang(): string {
  try {
    const saved = localStorage.getItem(LANG_KEY);
    if (saved && LANGS.some((l) => l.code === saved)) return saved;
  } catch {
    /* private mode / storage disabled */
  }
  return LANGS[0].code;
}

/**
 * Writing, speaking and reading aloud, in one place.
 *
 * They were three separate destinations, but they're the same activity —
 * producing the language rather than reviewing it — and they all need the same
 * two things: a target language and (optionally) a book to draw material from.
 * Merging them means you pick those once, and the nav loses an item.
 *
 * The tab lives in the URL (`/app/practice/speak`) so back/forward work and a
 * link points at the tab you meant.
 */
export default function Practice() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { tab: tabParam } = useParams<{ tab: string }>();
  const tab: Tab = TABS.includes(tabParam as Tab) ? (tabParam as Tab) : "write";

  const [language, setLanguage] = useState(storedLang);
  const [books, setBooks] = useState<WritingBook[]>([]);
  const [booksLoading, setBooksLoading] = useState(true);
  const tablist = useRef<HTMLDivElement>(null);

  // Fetched once here rather than per tab — Write and Read both want the list.
  useEffect(() => {
    writingBooks()
      .then(setBooks)
      .catch(() => {})
      .finally(() => setBooksLoading(false));
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(LANG_KEY, language);
    } catch {
      /* ignore */
    }
  }, [language]);

  // Normalise a bad/absent tab segment so the URL always names the visible tab.
  useEffect(() => {
    if (tabParam !== tab) navigate(`/app/practice/${tab}`, { replace: true });
  }, [tabParam, tab, navigate]);

  /** Arrow keys move between tabs, as a tablist is expected to. */
  function onTabKey(e: React.KeyboardEvent) {
    const delta = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!delta) return;
    e.preventDefault();
    const next = TABS[(TABS.indexOf(tab) + delta + TABS.length) % TABS.length];
    navigate(`/app/practice/${next}`);
    // Move focus with the selection, so the next arrow press continues from here.
    tablist.current?.querySelector<HTMLButtonElement>(`[data-tab="${next}"]`)?.focus();
  }

  return (
    <div className="practice">
      <div className="practice__head">
        <div>
          <h1>{t("practice.title")}</h1>
          <p className="practice__sub">{t(`practice.sub_${tab}`)}</p>
        </div>
        <label className="inlinefield practice__lang">
          <span>{t("practice.languageLabel")}</span>
          <select
            className="input input--sm"
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
          >
            {LANGS.map((l) => (
              <option key={l.code} value={l.code}>{l.name}</option>
            ))}
          </select>
        </label>
      </div>

      <div
        className="segmented practice__tabs"
        role="tablist"
        aria-label={t("practice.title")}
        ref={tablist}
        onKeyDown={onTabKey}
      >
        {TABS.map((key) => (
          <button
            key={key}
            data-tab={key}
            role="tab"
            id={`practice-tab-${key}`}
            aria-selected={tab === key}
            aria-controls="practice-panel"
            tabIndex={tab === key ? 0 : -1}
            className={`segmented__btn ${tab === key ? "segmented__btn--on" : ""}`}
            onClick={() => navigate(`/app/practice/${key}`)}
          >
            <span className="segmented__icon" aria-hidden>
              {key === "write" ? "✎" : key === "speak" ? "🎙" : "📖"}
            </span>
            {t(`practice.tab_${key}`)}
          </button>
        ))}
      </div>

      <div id="practice-panel" role="tabpanel" aria-labelledby={`practice-tab-${tab}`}>
        {/* Keyed by language so a tab switch keeps its state, but changing the
            target language starts that tab clean. */}
        {tab === "write" && (
          <WritePanel key={language} language={language} books={books} booksLoading={booksLoading} />
        )}
        {tab === "speak" && <SpeakPanel language={language} />}
        {tab === "read" && <ReadPanel language={language} books={books} />}
      </div>
    </div>
  );
}
