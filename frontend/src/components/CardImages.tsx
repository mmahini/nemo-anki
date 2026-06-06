import { useState } from "react";

import { addCardImage, deleteCardImage, findCardImage, type Card } from "../auth/api";

/** Manage a card's photos (shown on the answer side during review). `onChange`
 * is called after any change so the parent can refresh the card. */
export default function CardImages({ card, onChange }: { card: Card; onChange: () => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const images = card.images ?? [];

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (!files.length) return;
    setBusy(true);
    setErr(null);
    try {
      for (const f of files) await addCardImage(card.id, f);
      onChange();
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(imageId: number) {
    setBusy(true);
    try {
      await deleteCardImage(card.id, imageId);
      onChange();
    } finally {
      setBusy(false);
    }
  }

  async function autoFind() {
    setBusy(true);
    setErr(null);
    try {
      await findCardImage(card.id);
      onChange();
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : "No image found.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="cardimages">
      <span className="cardimages__label">
        Photos (shown on the answer)
        <button type="button" className="btn btn--ghost btn--sm cardimages__find" disabled={busy} onClick={autoFind}>
          {images.length ? "🔄 Regenerate image" : "🔍 Find image"}
        </button>
      </span>
      <div className="cardimages__grid">
        {images.map((im) => (
          <div key={im.id} className="cardimages__item">
            <img src={im.url} alt="" />
            <button type="button" className="cardimages__del" disabled={busy} onClick={() => remove(im.id)}>✕</button>
          </div>
        ))}
        <label className={`cardimages__add ${busy ? "is-busy" : ""}`}>
          {busy ? "…" : "+ Photo"}
          <input type="file" accept="image/*" multiple hidden onChange={onPick} disabled={busy} />
        </label>
      </div>
      {err && <p className="auth__error">{err}</p>}
    </div>
  );
}
