import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { seedStarterDecks } from "../auth/api";

/** Quiz setup — a top-level page inside the shell, so the mobile tab bar
 * stays visible. Picking language + length here; the test itself runs
 * full-screen (no chrome) at /app/placement-test/run. */
export default function PlacementTest() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [language, setLanguage] = useState<"de" | "en">("de");
  const [length, setLength] = useState<"quick" | "full">("quick");
  const [skipping, setSkipping] = useState(false);

  // Skipping the quiz still needs to leave the account with something to
  // study — seed the starter decks here since submitting a test is no
  // longer the only path into the deck list.
  async function skip() {
    setSkipping(true);
    try {
      await seedStarterDecks();
    } catch {
      // Not fatal — the deck list will just be empty until they retry.
    } finally {
      navigate("/app");
    }
  }

  return (
    <div className="ptsetup">
      <div className="reviewcard pt-intro">
        <h1>{t("placementTest.title")}</h1>
        <p className="pt-intro__desc">{t("placementTest.description")}</p>

        <label className="field">
          <span className="field__label">{t("placementTest.languageLabel")}</span>
          <div className="segmented">
            <button
              type="button"
              className={`segmented__btn ${language === "de" ? "segmented__btn--on" : ""}`}
              onClick={() => setLanguage("de")}
            >
              {t("common.german")}
            </button>
            <button
              type="button"
              className={`segmented__btn ${language === "en" ? "segmented__btn--on" : ""}`}
              onClick={() => setLanguage("en")}
            >
              {t("common.english")}
            </button>
          </div>
        </label>

        <label className="field">
          <span className="field__label">{t("placementTest.lengthLabel")}</span>
          <div className="segmented">
            <button
              type="button"
              className={`segmented__btn ${length === "quick" ? "segmented__btn--on" : ""}`}
              onClick={() => setLength("quick")}
            >
              {t("placementTest.lengthQuick")}
            </button>
            <button
              type="button"
              className={`segmented__btn ${length === "full" ? "segmented__btn--on" : ""}`}
              onClick={() => setLength("full")}
            >
              {t("placementTest.lengthFull")}
            </button>
          </div>
        </label>

        <button
          className="btn btn--primary btn--lg pt-intro__start"
          onClick={() => navigate("/app/placement-test/run", { state: { language, length } })}
        >
          {t("placementTest.startBtn")}
        </button>

        <button
          type="button"
          className="btn btn--ghost btn--sm pt-intro__skip"
          disabled={skipping}
          onClick={skip}
        >
          {t("placementTest.skipBtn")}
        </button>
      </div>
    </div>
  );
}
