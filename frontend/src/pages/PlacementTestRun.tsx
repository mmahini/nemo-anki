import { useEffect, useRef, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import {
  startPlacementTest,
  submitPlacementTest,
  type PlacementLevel,
  type PlacementQuestion,
  type PlacementResult,
} from "../auth/api";
import { speak } from "../lib/tts";

type Stage = "loading" | "question" | "result";

type RunState = { language: "de" | "en"; length: "quick" | "full" };

/** The test itself: full-screen and chrome-free (same shell as Study) — no
 * tab bar once the quiz has started. Reached only from the setup page, which
 * passes language + length via router state. */
export default function PlacementTestRun() {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();
  const run = (location.state ?? null) as RunState | null;

  const [stage, setStage] = useState<Stage>("loading");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [attemptId, setAttemptId] = useState<number | null>(null);
  const [questions, setQuestions] = useState<PlacementQuestion[]>([]);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [result, setResult] = useState<PlacementResult | null>(null);
  const started = useRef(false);

  const current = questions[index];
  const selected = current ? answers[current.id] : undefined;

  useEffect(() => {
    if (!run || started.current) return;
    started.current = true;
    startPlacementTest(run.language, run.length)
      .then((res) => {
        setAttemptId(res.attempt_id);
        setQuestions(res.questions);
        setStage("question");
      })
      .catch((e) => setError(e instanceof Error ? e.message : t("common.error")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Listening questions play automatically once, so the audio is the only
  // way to first hear the text (matches how a real listening section works).
  useEffect(() => {
    if (run && stage === "question" && current?.section === "listening" && current.audio_text) {
      speak(current.audio_text, run.language, { auto: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage, index]);

  // Deep link / refresh without setup state: back to the setup page.
  if (!run) return <Navigate to="/app/placement-test" replace />;

  function backToSetup() {
    navigate("/app/placement-test");
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
        <button className="btn btn--ghost btn--sm" onClick={backToSetup}>
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

      {stage === "loading" && !error && (
        <div className="study__stage">
          <div className="reviewcard pt-intro">
            <h1>{t("placementTest.title")}</h1>
            <p className="pt-intro__desc">{t("placementTest.starting")}</p>
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
                onClick={() => speak(current.audio_text, run.language)}
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
          <button
            className="btn btn--primary"
            onClick={() =>
              navigate(result.deck_id ? `/app/decks/${result.deck_id}` : "/app")
            }
          >
            {result.deck_id
              ? t("placementTest.goToDeckBtn", { level: result.estimated_level })
              : t("placementTest.backHome")}
          </button>
        </div>
      )}
    </div>
  );
}
