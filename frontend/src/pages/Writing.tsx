import { useState } from "react";
import { Link } from "react-router-dom";

import {
  writingCheck,
  writingToCard,
  writingTopic,
  type WritingIssue,
} from "../auth/api";

const LANGS = [
  { code: "de", name: "German" },
  { code: "en", name: "English" },
  { code: "fr", name: "French" },
  { code: "es", name: "Spanish" },
  { code: "it", name: "Italian" },
];

export default function Writing() {
  const [language, setLanguage] = useState("de");
  const [topic, setTopic] = useState<{ topic: string; en: string } | null>(null);
  const [text, setText] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [issues, setIssues] = useState<WritingIssue[] | null>(null);
  const [busyTopic, setBusyTopic] = useState(false);
  const [busyCheck, setBusyCheck] = useState(false);
  const [added, setAdded] = useState<Record<number, string>>({});
  const [adding, setAdding] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function suggestTopic() {
    setBusyTopic(true);
    setError(null);
    try {
      setTopic(await writingTopic(language));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't suggest a topic.");
    } finally {
      setBusyTopic(false);
    }
  }

  async function check() {
    if (!text.trim()) return;
    setBusyCheck(true);
    setError(null);
    setIssues(null);
    setFeedback(null);
    setAdded({});
    try {
      const r = await writingCheck(text, language);
      setIssues(r.issues);
      setFeedback(r.feedback);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Check failed.");
    } finally {
      setBusyCheck(false);
    }
  }

  async function addCard(issue: WritingIssue, i: number) {
    setAdding(i);
    try {
      const res = await writingToCard({
        language,
        front: issue.correction || issue.original,
        back: issue.explanation,
        notes: issue.original ? `You wrote: ${issue.original}` : "",
      });
      setAdded((a) => ({ ...a, [i]: res.deck_name }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't add the card.");
    } finally {
      setAdding(null);
    }
  }

  return (
    <div className="writing">
      <h1>Writing</h1>
      <p className="import__sub">
        Practise free writing, get it corrected, and turn each mistake into a sentence card.
      </p>

      <div className="writing__bar">
        <label className="cardeditor__field">
          <span>Language</span>
          <select className="input" value={language} onChange={(e) => setLanguage(e.target.value)}>
            {LANGS.map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}
          </select>
        </label>
        <button className="btn btn--ghost" disabled={busyTopic} onClick={suggestTopic}>
          {busyTopic ? "Thinking…" : "💡 Suggest a topic"}
        </button>
      </div>

      {topic && (
        <div className="panel writing__topic">
          <strong>{topic.topic}</strong>
          {topic.en && <span className="writing__topicen">{topic.en}</span>}
        </div>
      )}

      <textarea
        className="import__textarea writing__textarea"
        rows={10}
        placeholder="Write here…"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <div className="writing__actions">
        <span className="writing__count">{text.trim() ? text.trim().split(/\s+/).length : 0} words</span>
        <button className="btn btn--primary" disabled={busyCheck || !text.trim()} onClick={check}>
          {busyCheck ? "Checking…" : "✓ Check & correct"}
        </button>
      </div>

      {error && <p className="auth__error">{error}</p>}

      {feedback && <div className="panel writing__feedback">💬 {feedback}</div>}

      {issues && (
        issues.length === 0 ? (
          <div className="panel writing__clean">🎉 No mistakes found — nice writing!</div>
        ) : (
          <div className="writing__issues">
            <div className="writing__issueshead">
              <strong>{issues.length} thing{issues.length === 1 ? "" : "s"} to fix</strong>
              <span className="browse__sub">Add any of them to “Writing problems ({language})”.</span>
            </div>
            {issues.map((it, i) => (
              <div key={i} className="issue">
                <div className="issue__top">
                  <span className="badge">{it.type}</span>
                  {added[i] ? (
                    <span className="issue__added">✓ added to {added[i]}</span>
                  ) : (
                    <button className="btn btn--ghost btn--sm" disabled={adding === i} onClick={() => addCard(it, i)}>
                      {adding === i ? "Adding…" : "+ Add as card"}
                    </button>
                  )}
                </div>
                {it.original && <div className="issue__bad">✗ {it.original}</div>}
                {it.correction && <div className="issue__good">✓ {it.correction}</div>}
                {it.explanation && <div className="issue__why">{it.explanation}</div>}
              </div>
            ))}
          </div>
        )
      )}

      {Object.keys(added).length > 0 && (
        <p className="writing__hint">
          Saved cards live in your decks — open <Link to="/app">Decks</Link> to study them.
        </p>
      )}
    </div>
  );
}
