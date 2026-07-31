import { useState } from "react";
import { useTranslation } from "react-i18next";

import { fetchCardForReview, updateCard, type Card, type DraftCard } from "../auth/api";
import CardEditor, { cardToDraft } from "./CardEditor";
import CardImages from "./CardImages";

/** Edit a card in place (used during review). Saves content via PATCH; photos
 * are managed live by CardImages. Calls onSaved with the refreshed card. */
export default function CardEditModal({
  card,
  onClose,
  onSaved,
}: {
  card: Card;
  onClose: () => void;
  onSaved: (updated: Card) => void;
}) {
  const { t } = useTranslation();
  const [state, setState] = useState<Card>(card);
  const [draft, setDraft] = useState<DraftCard>(() => cardToDraft(card));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function refreshImages() {
    const fresh = await fetchCardForReview(card.id).catch(() => null);
    if (fresh) {
      setState(fresh);
      onSaved(fresh); // reflect new photos behind the modal immediately
    }
  }

  async function save() {
    setBusy(true);
    setErr(null);
    try {
      const updated = await updateCard(card.id, draft);
      onSaved(updated);
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : t("cardEditor.errSave"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="lessonview" onClick={onClose}>
      <div className="lessonview__card editmodal" onClick={(e) => e.stopPropagation()}>
        <div className="lessonview__head">
          <strong>{t("cardEditor.editTitle")}</strong>
          <button className="btn btn--ghost btn--sm" onClick={onClose}>{t("common.close")}</button>
        </div>
        <div className="editmodal__body">
          <CardEditor value={draft} onChange={setDraft} />
          <CardImages card={state} onChange={refreshImages} />
          {err && <p className="auth__error">{err}</p>}
        </div>
        <div className="editmodal__foot">
          <button className="btn btn--ghost" onClick={onClose}>{t("common.cancel")}</button>
          <button className="btn btn--primary" disabled={busy} onClick={save}>
            {busy ? t("common.saving") : t("common.save")}
          </button>
        </div>
      </div>
    </div>
  );
}
