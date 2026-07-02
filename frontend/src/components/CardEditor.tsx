import { useState } from "react";

import {
  analyzeGerman,
  conjugateVerb,
  enrichCard,
  type Article,
  type Card,
  type CardType,
  type Conjugation,
  type DraftCard,
} from "../auth/api";
import { detectArticle } from "../lib/article";
import { getTranslateLang, setTranslateLang, TRANSLATE_LANGS } from "../lib/translateLang";
import CaseTable from "./CaseTable";
import SpeakButton from "./SpeakButton";

const CARD_TYPES: CardType[] = ["vocab", "sentence", "grammar", "verb"];
const ARTICLES: Article[] = ["none", "der", "die", "das", "plural"];

export function emptyDraft(language: "de" | "en" | "" = "", card_type: CardType = "vocab"): DraftCard {
  return {
    card_type,
    language,
    front: "",
    back: "",
    reading: "",
    article: "none",
    plural: "",
    example: "",
    notes: "",
    table: null,
    genders: [],
    conjugations: [],
    tags: [],
  };
}

/** Snapshot a saved card's editable content into a draft for the editor. */
export function cardToDraft(c: Card): DraftCard {
  return {
    card_type: c.card_type,
    language: c.language as DraftCard["language"],
    front: c.front,
    back: c.back,
    reading: c.reading,
    article: c.article,
    plural: c.plural,
    example: c.example,
    notes: c.notes,
    table: c.table,
    genders: c.genders,
    conjugations: c.conjugations ?? [],
    tags: c.tags,
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
  const [analyzing, setAnalyzing] = useState(false);
  const [conjugating, setConjugating] = useState(false);
  // Language the translation (back) is written in — defaults to the last used.
  const [backLang, setBackLang] = useState(getTranslateLang);

  const set = <K extends keyof DraftCard>(key: K, v: DraftCard[K]) =>
    onChange({ ...value, [key]: v });

  const isGerman = value.language === "de";
  const isSentence = value.card_type === "sentence";
  const isVerb = value.card_type === "verb";
  const hasReading = value.card_type === "vocab" || isSentence || isVerb;
  const showArticle = isGerman && value.card_type === "vocab";
  // Accurate colouring only matters for multi-word German noun/sentence cards.
  const showColourGenders = isGerman && value.card_type !== "vocab" && !isVerb;

  // Editing the front invalidates a previous gender analysis.
  function onFrontChange(v: string) {
    onChange({ ...value, front: v, genders: [] });
  }

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
        back_language: backLang,
      });
      onChange({
        ...value,
        back: r.back || value.back,
        reading: r.reading || value.reading,
        article: r.article && r.article !== "none" ? r.article : value.article,
        // Plural form is only meaningful for vocab nouns.
        plural: value.card_type === "vocab" ? r.plural || value.plural : value.plural,
        // A sentence card is its own example — don't add a separate one.
        example: isSentence ? "" : r.example || value.example,
      });
    } catch (err) {
      setTranslateErr(err instanceof Error ? err.message : "Translate failed.");
    } finally {
      setTranslating(false);
    }
  }

  async function colourGenders() {
    if (!value.front.trim()) return;
    setAnalyzing(true);
    setTranslateErr(null);
    try {
      const r = await analyzeGerman(value.front.trim());
      onChange({ ...value, genders: r.nouns });
    } catch (err) {
      setTranslateErr(err instanceof Error ? err.message : "Analysis failed.");
    } finally {
      setAnalyzing(false);
    }
  }

  // AI-fill the verb's conjugations (and the meaning if it's still empty).
  async function fillConjugations() {
    if (!value.front.trim()) return;
    setConjugating(true);
    setTranslateErr(null);
    try {
      const r = await conjugateVerb({
        front: value.front.trim(),
        language: (value.language as any) || undefined,
        back_language: backLang,
      });
      onChange({
        ...value,
        conjugations: r.conjugations.length ? r.conjugations : value.conjugations,
        back: value.back || r.back,
      });
    } catch (err) {
      setTranslateErr(err instanceof Error ? err.message : "Couldn't conjugate the verb.");
    } finally {
      setConjugating(false);
    }
  }

  const setConj = (rows: Conjugation[]) => set("conjugations", rows);
  const addConjRow = () => setConj([...value.conjugations, { tense: "", form: "", meaning: "" }]);
  const updateConjRow = (i: number, key: keyof Conjugation, v: string) =>
    setConj(value.conjugations.map((r, j) => (j === i ? { ...r, [key]: v } : r)));
  const removeConjRow = (i: number) => setConj(value.conjugations.filter((_, j) => j !== i));

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
        <div className="cardeditor__tools">
          {showColourGenders && (
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={colourGenders}
              disabled={analyzing || !value.front.trim()}
              title="Detect each noun's true gender and colour the sentence accurately"
            >
              {analyzing
                ? "Analysing…"
                : value.genders.length
                  ? `🎨 ${value.genders.length} coloured`
                  : "🎨 Colour genders"}
            </button>
          )}
          <div className="translate-group" title="Translate the back into this language">
            <select
              className="input input--sm translate-group__lang"
              value={backLang}
              onChange={(e) => {
                setBackLang(e.target.value);
                setTranslateLang(e.target.value);
              }}
            >
              {TRANSLATE_LANGS.map((l) => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
            <button
              type="button"
              className="btn btn--ghost btn--sm translate-group__btn"
              onClick={translate}
              disabled={translating || !value.front.trim()}
              title="Auto-translate + fill reading/article"
            >
              {translating ? "Translating…" : "🌐 Translate"}
            </button>
          </div>
        </div>
      </div>

      <label className="cardeditor__field">
        <span>{value.card_type === "grammar" ? "Prompt (use ___ for the gap)" : "Front"}</span>
        <div className="cardeditor__inline cardeditor__inline--top">
          <textarea
            className="input cardeditor__text"
            rows={2}
            value={value.front}
            onChange={(e) => onFrontChange(e.target.value)}
            onBlur={onFrontBlur}
            placeholder={showArticle ? "e.g. der Tisch — article is detected" : ""}
          />
          <SpeakButton text={value.front} lang={value.language} title="Hear the front" />
        </div>
        {showColourGenders && value.genders.length > 0 && (
          <div className="cardeditor__cases">
            <CaseTable items={value.genders} />
          </div>
        )}
      </label>

      <label className="cardeditor__field">
        <span>{value.card_type === "grammar" ? "Answer (fills the gap)" : "Back / translation"}</span>
        <textarea className="input cardeditor__text" rows={2} dir="auto" value={value.back} onChange={(e) => set("back", e.target.value)} />
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

      {value.card_type === "vocab" && (
        <label className="cardeditor__field">
          <span>Plural</span>
          <div className="cardeditor__inline">
            <input
              className="input"
              value={value.plural}
              onChange={(e) => set("plural", e.target.value)}
              placeholder="e.g. die Tische"
            />
            <SpeakButton text={value.plural} lang={value.language} title="Hear the plural" />
          </div>
        </label>
      )}

      {translateErr && <p className="auth__error">{translateErr}</p>}

      {!compact && (
        <>
          {isVerb && (
            <div className="cardeditor__field">
              <div className="cardeditor__conjhead">
                <span>Conjugations</span>
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  onClick={fillConjugations}
                  disabled={conjugating || !value.front.trim()}
                  title="Fill the verb's forms for each tense/situation with AI"
                >
                  {conjugating ? "Filling…" : "🪄 Fill conjugations"}
                </button>
              </div>
              {value.conjugations.length > 0 && (
                <div className="conjeditor">
                  {value.conjugations.map((row, i) => (
                    <div key={i} className="conjeditor__row">
                      <input
                        className="input input--sm conjeditor__tense"
                        value={row.tense}
                        onChange={(e) => updateConjRow(i, "tense", e.target.value)}
                        placeholder="Tense"
                      />
                      <div className="conjeditor__form">
                        <input
                          className="input input--sm"
                          value={row.form}
                          onChange={(e) => updateConjRow(i, "form", e.target.value)}
                          placeholder="Form"
                        />
                        <SpeakButton text={row.form} lang={value.language} small title="Hear this form" />
                      </div>
                      <input
                        className="input input--sm conjeditor__meaning"
                        dir="auto"
                        value={row.meaning}
                        onChange={(e) => updateConjRow(i, "meaning", e.target.value)}
                        placeholder="Meaning"
                      />
                      <button
                        type="button"
                        className="conjeditor__del"
                        onClick={() => removeConjRow(i)}
                        title="Remove this row"
                        aria-label="Remove row"
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>
              )}
              <button type="button" className="btn btn--ghost btn--sm conjeditor__add" onClick={addConjRow}>
                + Add row
              </button>
            </div>
          )}
          {/* A sentence card is itself the example — no separate Example field. */}
          {!isSentence && (
            <label className="cardeditor__field">
              <span>Example</span>
              <div className="cardeditor__inline cardeditor__inline--top">
                <textarea
                  className="input cardeditor__text"
                  rows={2}
                  dir="auto"
                  value={value.example}
                  onChange={(e) => set("example", e.target.value)}
                  placeholder="One example per line"
                />
                <SpeakButton text={value.example} lang={value.language} title="Hear the example" />
              </div>
            </label>
          )}
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
