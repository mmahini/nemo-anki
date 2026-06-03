import type { Article, CardType, DraftCard } from "../auth/api";

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
  const set = <K extends keyof DraftCard>(key: K, v: DraftCard[K]) =>
    onChange({ ...value, [key]: v });

  const isGerman = value.language === "de";
  const hasReading = value.card_type === "vocab" || value.card_type === "sentence";

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
        {isGerman && value.card_type === "vocab" && (
          <select
            className={`input input--sm art-select art-select--${value.article}`}
            value={value.article}
            onChange={(e) => set("article", e.target.value as Article)}
          >
            {ARTICLES.map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>
        )}
      </div>

      <label className="cardeditor__field">
        <span>{value.card_type === "grammar" ? "Prompt (use ___ for the gap)" : "Front"}</span>
        <input className="input" value={value.front} onChange={(e) => set("front", e.target.value)} />
      </label>

      <label className="cardeditor__field">
        <span>{value.card_type === "grammar" ? "Answer (fills the gap)" : "Back / translation"}</span>
        <input className="input" value={value.back} onChange={(e) => set("back", e.target.value)} />
      </label>

      {hasReading && (
        <label className="cardeditor__field">
          <span>Reading (phonetic)</span>
          <input className="input mono" value={value.reading} onChange={(e) => set("reading", e.target.value)} />
        </label>
      )}

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
