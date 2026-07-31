import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import {
  startPlacementTest,
  submitPlacementTest,
  type PlacementLevel,
  type PlacementQuestion,
  type PlacementResult,
} from "../auth/api";
import { speak } from "../lib/tts";

type Stage = "intro" | "question" | "result";

/** Full-screen, chrome-free flow (same shell as Study): pick language + length,
 * answer one AI-generated Reading/Listening question at a time, see an
 * estimated CEFR level at the end. Entered from a link on the Decks page, not
 * from the nav bar — same off-nav pattern as Import. */
export default function PlacementTest() {
  const navigate = useNavigate();
  const { t } = useTranslation();

  const [stage, setStage] = useState<Stage>("intro");
  const [language, setLanguage] = useState<"de" | "en">("de");
  const [length, setLength] = useState<"quick" | "full">("quick");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [attemptId, setAttemptId] = useState<number | null>(null);
  const [questions, setQuestions] = useState<PlacementQuestion[]>([]);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [result, setResult] = useState<PlacementResult | null>(null);

  const current = questions[index];
  const selected = current ? answers[current.id] : undefined;

  // Listening questions play automatically once, so the audio is the only
  // way to first hear the text (matches how a real listening section works).
  useEffect(() => {
    if (stage === "question" && current?.section === "listening" && current.audio_text) {
      speak(current.audio_text, language);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage, index]);

  function backToDecks() {
    navigate("/app");
  }

  async function start() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await startPlacementTest(language, length);
      setAttemptId(res.attempt_id);
      setQuestions(res.questions);
      setIndex(0);
      setAnswers({});
      setStage("question");
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  function selectChoice(choiceIndex: number) {
    if (!current) return;
    setAnswers((prev) => ({ ...prev, [current.id]: choiceIndex }));
  }

  async function finish(finalAnswers: Record<number, number>) {
    if (!attemptId || busy) return;
    setBusy(true);
    setError(null);
    try {
      const payload = Object.entries(finalAnswers).map(([questionId, choiceIndex]) => ({
        question_id: Number(questionId),
        choice_index: choiceIndex,
      }));
      const res = await submitPlacementTest(attemptId, payload);
      setResult(res);
      setStage("result");
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  function next() {
    if (index + 1 < questions.length) {
      setIndex((i) => i + 1);
    } else {
      void finish(answers);
    }
  }

  const levelOrder: PlacementLevel[] = ["A1", "A2", "B1", "B2", "C1"];

  return (
    <div className="study">
      <header className="study__bar">
        <button className="btn btn--ghost btn--sm" onClick={backToDecks}>
          {t("placementTest.backBtn")}
        </button>
        {stage === "question" && (
          <span className="study__progress">
            <span className="count count--due">
              {t("placementTest.progress", { current: index + 1, total: questions.length })}
            </span>
          </span>
        )}
        <span />
      </header>

      {error && <div className="panel panel--error">{error}</div>}

      {stage === "intro" && (
        <div className="study__stage">
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

            <button className="btn btn--primary btn--lg pt-intro__start" disabled={busy} onClick={start}>
              {busy ? t("placementTest.starting") : t("placementTest.startBtn")}
            </button>
          </div>
        </div>
      )}

      {stage === "question" && current && (
        <div className="study__stage">
          <div className="reviewcard pt-question">
            <span className="pt-question__level">
              {current.level_tag} · {t(`placementTest.section.${current.section}`)}
            </span>
            {current.section === "reading" ? (
              <p className="pt-question__passage">{current.passage}</p>
            ) : (
              <button
                type="button"
                className="btn btn--ghost pt-question__play"
                onClick={() => speak(current.audio_text, language)}
              >
                🔊 {t("placementTest.playAgain")}
              </button>
            )}
            <p className="pt-question__prompt">{current.question_text}</p>
            <div className="mcq">
              {current.choices.map((choice, i) => (
                <button
                  key={i}
                  type="button"
                  className={`mcq__option ${selected === i ? "is-selected" : ""}`}
                  onClick={() => selectChoice(i)}
                >
                  {choice}
                </button>
              ))}
            </div>
          </div>
          <button
            className="btn btn--primary btn--lg study__show"
            disabled={selected === undefined || busy}
            onClick={next}
          >
            {index + 1 < questions.length ? t("placementTest.nextBtn") : t("placementTest.finishBtn")}
          </button>
        </div>
      )}

      {stage === "result" && result && (
        <div className="study__done">
          <div className="study__done-emoji">🎓</div>
          <h2>{t("placementTest.resultTitle")}</h2>
          <div className="pt-result__level">{result.estimated_level}</div>
          <p>{t("placementTest.resultScore", { correct: result.correct_count, total: result.total_count })}</p>
          <div className="dashboard__tiles pt-result__levels">
            {levelOrder
              .filter((lvl) => result.by_level[lvl])
              .map((lvl) => (
                <div key={lvl} className="dashboard__tile">
                  <span className="tile__label">{lvl}</span>
                  <span className="tile__value">
                    {result.by_level[lvl].correct}/{result.by_level[lvl].total}
                  </span>
                </div>
              ))}
          </div>
          <button className="btn btn--primary" onClick={backToDecks}>
            {t("placementTest.backToDecks")}
          </button>
        </div>
      )}
    </div>
  );
}
