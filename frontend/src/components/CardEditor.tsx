import { useState } from "react";

import { enrichCard, type Article, type CardType, type DraftCard } from "../auth/api";
import { detectArticle } from "../lib/article";
import SpeakButton from "./SpeakButton";

const CARD_TYPES: CardType[] = ["vocab", "sentence", "grammar"];
const ARTICLES: Article[] = ["none", "der", "die", "das", "plural"];

export function emptyDraft(language: "de" | "en" | "" = "", card_type: CardType = "vocab"): DraftCard {
  return {
    card_type,
    language,
    front: "",
    back: "",
    reading: "",
    article: "none",
    example: "",
    notes: "",
    table: null,
    tags: [],
  };
}

type Props = {
  value: DraftCard;
  onChange: (next: DraftCard) => void;
  compact?: boolean;
};

export default function CardEditor({ value, onChange, compact }: Props) {
  const [translating, setTranslating] = useState(false);
  const [translateErr, setTranslateErr] = useState<string | null>(null);

  const set = <K extends keyof DraftCard>(key: K, v: DraftCard[K]) =>
    onChange({ ...value, [key]: v });

  const isGerman = value.language === "de";
  const hasReading = value.card_type === "vocab" || value.card_type === "sentence";
  const showArticle = isGerman && value.card_type === "vocab";

  // Strip a leading "der/die/das " off the typed word into the article field.
  function onFrontBlur() {
    if (!showArticle) return;
    const d = detectArticle(value.front);
    if (d) onChange({ ...value, front: d.rest, article: d.article });
  }

  async function translate() {
    if (!value.front.trim()) return;
    setTranslating(true);
    setTranslateErr(null);
    try {
      const r = await enrichCard({
        front: value.front.trim(),
        language: (value.language as any) || undefined,
        card_type: value.card_type,
      });
      onChange({
        ...value,
        back: r.back || value.back,
        reading: r.reading || value.reading,
        // Only override the article when the server is confident (non-"none").
        article: r.article && r.article !== "none" ? r.article : value.article,
        example: r.example || value.example,
      });
    } catch (err) {
      setTranslateErr(err instanceof Error ? err.message : "Translate failed.");
    } finally {
      setTranslating(false);
    }
  }

  return (
    <div className={`cardeditor ${compact ? "cardeditor--compact" : ""}`}>
      <div className="cardeditor__row">
        <select
          className="input input--sm"
          value={value.card_type}
          onChange={(e) => set("card_type", e.target.value as CardType)}
        >
          {CARD_TYPES.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        {showArticle && (
          <select
            className={`input input--sm art-select art-select--${value.article}`}
            value={value.article}
            onChange={(e) => set("article", e.target.value as Article)}
            title="German article (colour-coded)"
          >
            {ARTICLES.map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>
        )}
        <button
          type="button"
          className="btn btn--ghost btn--sm cardeditor__translate"
          onClick={translate}
          disabled={translating || !value.front.trim()}
          title="Auto-translate + fill reading/article"
        >
          {translating ? "Translating…" : "🌐 Translate"}
        </button>
      </div>

      <label className="cardeditor__field">
        <span>{value.card_type === "grammar" ? "Prompt (use ___ for the gap)" : "Front"}</span>
        <div className="cardeditor__inline">
          <input
            className="input"
            value={value.front}
            onChange={(e) => set("front", e.target.value)}
            onBlur={onFrontBlur}
            placeholder={showArticle ? "e.g. der Tisch — article is detected" : ""}
          />
          <SpeakButton text={value.front} lang={value.language} title="Hear the front" />
        </div>
      </label>

      <label className="cardeditor__field">
        <span>{value.card_type === "grammar" ? "Answer (fills the gap)" : "Back / translation"}</span>
        <input className="input" value={value.back} onChange={(e) => set("back", e.target.value)} />
      </label>

      {hasReading && (
        <label className="cardeditor__field">
          <span>Reading (phonetic)</span>
          <div className="cardeditor__inline">
            <input
              className="input mono"
              value={value.reading}
              onChange={(e) => set("reading", e.target.value)}
              placeholder="/ˈtɪʃ/"
            />
            <SpeakButton text={value.front} lang={value.language} title="Hear pronunciation" />
          </div>
        </label>
      )}

      {translateErr && <p className="auth__error">{translateErr}</p>}

      {!compact && (
        <>
          <label className="cardeditor__field">
            <span>Example</span>
            <input className="input" value={value.example} onChange={(e) => set("example", e.target.value)} />
          </label>
          {value.card_type === "grammar" && (
            <label className="cardeditor__field">
              <span>Rule / notes</span>
              <input className="input" value={value.notes} onChange={(e) => set("notes", e.target.value)} />
            </label>
          )}
          <label className="cardeditor__field">
            <span>Tags (comma-separated)</span>
            <input
              className="input"
              value={value.tags.join(", ")}
              onChange={(e) =>
                set("tags", e.target.value.split(",").map((t) => t.trim()).filter(Boolean))
              }
            />
          </label>
        </>
      )}
    </div>
  );
}
