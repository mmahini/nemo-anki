import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { createCard, fetchDecks, type Deck } from "../auth/api";
import CardEditor, { emptyDraft } from "../components/CardEditor";
import { CardBack, CardFront } from "../components/CardFace";

export default function AddCard() {
  const { deckId } = useParams();
  const navigate = useNavigate();
  const id = Number(deckId);
  const [deck, setDeck] = useState<Deck | null>(null);
  const [draft, setDraft] = useState(emptyDraft());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedCount, setSavedCount] = useState(0);

  useEffect(() => {
    fetchDecks().then((decks) => {
      const d = decks.find((x) => x.id === id) ?? null;
      setDeck(d);
      setDraft((prev) => ({ ...prev, language: d?.language ?? "" }));
    });
  }, [id]);

  async function save(addAnother: boolean) {
    if (!draft.front.trim()) {
      setError("Front can't be empty.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await createCard({ ...draft, deck: id });
      setSavedCount((n) => n + 1);
      if (addAnother) {
        setDraft(emptyDraft(deck?.language ?? "", draft.card_type));
      } else {
        navigate(`/app/decks/${id}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save card.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="addcard">
      <div className="addcard__head">
        <button className="btn btn--ghost btn--sm" onClick={() => navigate(`/app/decks/${id}`)}>
          ← {deck?.full_name ?? "Deck"}
        </button>
        <h1>Add a card</h1>
        {savedCount > 0 && <span className="addcard__saved">{savedCount} added</span>}
      </div>

      <div className="addcard__grid">
        <div className="addcard__form">
          <CardEditor value={draft} onChange={setDraft} />
          {error && <p className="auth__error">{error}</p>}
          <div className="addcard__actions">
            <button className="btn btn--primary" disabled={saving} onClick={() => save(true)}>
              Save &amp; add another
            </button>
            <button className="btn btn--ghost" disabled={saving} onClick={() => save(false)}>
              Save &amp; done
            </button>
          </div>
        </div>

        <div className="addcard__preview">
          <div className="preview-label">Preview</div>
          <div className="reviewcard reviewcard--static">
            <CardFront card={draft} />
            <hr className="reviewcard__rule" />
            <CardBack card={draft} />
          </div>
        </div>
      </div>
    </div>
  );
}
