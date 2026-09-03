import { useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  AuthRequiredError,
  attachCardImage,
  createCard,
  enrichCard,
  enrichImage,
  enrichVoice,
  fetchDecks,
  fetchMe,
} from "../lib/api";
import type { Article, CardType, Deck } from "../lib/types";

type Category = "word" | "sentence";
type Mode = "text" | "voice" | "image";
type Status = "loading" | "record" | "transcribing" | "ready" | "signed-out" | "no-decks" | "error";

// EnrichRequestSerializer caps `front` at 500 chars server-side (backend/apps/
// imports/views.py) — truncate up front so a long selection can't 400.
const MAX_FRONT_LENGTH = 500;
const LAST_DECK_KEY_PREFIX = "nemo-anki-ext.lastDeck.";

// Mirrors the crude word-count heuristic the backend's own import fallback uses
// (apps/imports/gemini.py, _parse_fallback) — just a hint for the enrich call;
// the AI's own judgement (returned in the response) is what actually drives the
// proposal, and the user can always flip the toggle themselves.
function guessCategory(text: string): Category {
  return text.trim().split(/\s+/).filter(Boolean).length > 4 ? "sentence" : "word";
}

function getCaptureId(): string | null {
  return new URLSearchParams(window.location.search).get("capture");
}

function getImageCaptureId(): string | null {
  return new URLSearchParams(window.location.search).get("image");
}

function getMode(): Mode {
  const params = new URLSearchParams(window.location.search);
  if (params.get("image")) return "image";
  return params.get("mode") === "voice" ? "voice" : "text";
}

export function Proposal() {
  const [mode] = useState<Mode>(getMode);
  const [status, setStatus] = useState<Status>("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [language, setLanguage] = useState<"de" | "en" | "">("");
  const [category, setCategory] = useState<Category>("word");
  const [wordCardType, setWordCardType] = useState<CardType>("vocab");
  const [front, setFront] = useState("");
  const [back, setBack] = useState("");
  const [reading, setReading] = useState("");
  const [example, setExample] = useState("");
  const [article, setArticle] = useState<Article>("none");
  const [plural, setPlural] = useState("");
  const [decks, setDecks] = useState<Deck[]>([]);
  const [deckId, setDeckId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState(false);
  const [recording, setRecording] = useState(false);
  const [imageDataUrl, setImageDataUrl] = useState<string | null>(null);
  const [imageAttachFailed, setImageAttachFailed] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  useEffect(() => {
    void init();
    // Runs once on mount to resolve the capture id/mode from the URL —
    // intentionally not re-run on any state change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function init() {
    let text = "";
    let guessedCategory: Category = "word";

    if (mode === "text") {
      const captureId = getCaptureId();
      if (!captureId) {
        setStatus("error");
        setErrorMessage("Nothing was captured — select some text and try again.");
        return;
      }
      const key = `capture:${captureId}`;
      const stored = await chrome.storage.session.get(key);
      const capture = stored[key] as { text: string } | undefined;
      if (!capture?.text) {
        setStatus("error");
        setErrorMessage("This capture expired — select the text again.");
        return;
      }
      void chrome.storage.session.remove(key);

      text = capture.text.slice(0, MAX_FRONT_LENGTH);
      setFront(text);
      guessedCategory = guessCategory(text);
      setCategory(guessedCategory);
    }

    let imageUrl = "";
    if (mode === "image") {
      const captureId = getImageCaptureId();
      if (!captureId) {
        setStatus("error");
        setErrorMessage("Nothing was captured — right-click the image again.");
        return;
      }
      const key = `image:${captureId}`;
      const stored = await chrome.storage.session.get(key);
      const capture = stored[key] as { imageUrl: string } | undefined;
      if (!capture?.imageUrl) {
        setStatus("error");
        setErrorMessage("This capture expired — right-click the image again.");
        return;
      }
      void chrome.storage.session.remove(key);
      imageUrl = capture.imageUrl;
    }

    try {
      const [me, deckList] = await Promise.all([fetchMe(), fetchDecks()]);
      const lang = (me.learning_languages[0] as "de" | "en" | undefined) ?? "";
      setLanguage(lang);
      setDecks(deckList);

      if (deckList.length === 0) {
        setStatus("no-decks");
        return;
      }

      const lastDeckKey = `${LAST_DECK_KEY_PREFIX}${lang}`;
      const lastDeckStored = await chrome.storage.local.get(lastDeckKey);
      const lastDeckId = lastDeckStored[lastDeckKey] as number | undefined;
      const defaultDeck = deckList.find((d) => d.id === lastDeckId) ?? deckList[0];
      setDeckId(defaultDeck.id);

      if (mode === "voice") {
        // No text yet — wait for a recording instead of enriching immediately.
        setStatus("record");
        return;
      }

      if (mode === "image") {
        const result = await enrichImage({
          image_url: imageUrl,
          language: lang,
          card_type: "vocab",
          back_language: "English",
        });
        setImageDataUrl(result.image_data_url);
        setFront(result.front);
        setBack(result.back);
        setReading(result.reading);
        setExample(result.example);
        setArticle(result.article);
        setPlural(result.plural);
        if (result.card_type === "sentence") {
          setCategory("sentence");
        } else if (result.card_type) {
          setCategory("word");
          setWordCardType(result.card_type);
        }
        setStatus("ready");
        return;
      }

      const result = await enrichCard({
        front: text,
        language: lang,
        card_type: guessedCategory === "sentence" ? "sentence" : "vocab",
      });
      setBack(result.back);
      setReading(result.reading);
      setExample(result.example);
      setArticle(result.article);
      setPlural(result.plural);
      if (result.card_type === "sentence") {
        setCategory("sentence");
      } else if (result.card_type) {
        setCategory("word");
        setWordCardType(result.card_type);
      }
      setStatus("ready");
    } catch (err) {
      if (err instanceof AuthRequiredError) {
        setStatus("signed-out");
        return;
      }
      setStatus("error");
      setErrorMessage(
        err instanceof ApiError ? err.message : "Couldn't reach Nemo Anki — check your connection.",
      );
    }
  }

  async function handleStartRecording() {
    setErrorMessage("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        void handleRecordingStopped();
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch {
      setErrorMessage("Microphone access was denied — allow it and try again.");
    }
  }

  function handleStopRecording() {
    mediaRecorderRef.current?.stop();
    setRecording(false);
  }

  async function handleRecordingStopped() {
    const mimeType = mediaRecorderRef.current?.mimeType || "audio/webm";
    const blob = new Blob(chunksRef.current, { type: mimeType });
    chunksRef.current = [];
    if (blob.size === 0) {
      setErrorMessage("Didn't catch any audio — try recording again.");
      return;
    }

    setStatus("transcribing");
    try {
      const result = await enrichVoice({
        audio: blob,
        language,
        card_type: "vocab",
        back_language: "English",
      });
      if (!result.front) {
        setErrorMessage("Couldn't make out what you said — try recording again.");
        setStatus("record");
        return;
      }
      setFront(result.front);
      setBack(result.back);
      setReading(result.reading);
      setExample(result.example);
      setArticle(result.article);
      setPlural(result.plural);
      if (result.card_type === "sentence") {
        setCategory("sentence");
      } else if (result.card_type) {
        setCategory("word");
        setWordCardType(result.card_type);
      }
      setStatus("ready");
    } catch (err) {
      if (err instanceof AuthRequiredError) {
        setStatus("signed-out");
        return;
      }
      setErrorMessage(
        err instanceof ApiError ? err.message : "Couldn't reach Nemo Anki — check your connection.",
      );
      setStatus("record");
    }
  }

  const cardType = useMemo<CardType>(
    () => (category === "sentence" ? "sentence" : wordCardType),
    [category, wordCardType],
  );

  async function handleCreate() {
    if (!deckId) return;
    setCreating(true);
    setErrorMessage("");
    try {
      const card = await createCard({
        deck: deckId,
        card_type: cardType,
        language,
        front,
        back,
        reading,
        article,
        plural,
        example,
      });
      await chrome.storage.local.set({ [`${LAST_DECK_KEY_PREFIX}${language}`]: deckId });
      if (imageDataUrl) {
        // Best-effort: the card is already saved, so a failed attach here
        // must never undo it or block the success screen — just flag it.
        try {
          const blob = await (await fetch(imageDataUrl)).blob();
          await attachCardImage(card.id, blob);
        } catch {
          setImageAttachFailed(true);
        }
      }
      setCreated(true);
      setTimeout(() => window.close(), 1200);
    } catch (err) {
      if (err instanceof AuthRequiredError) {
        setStatus("signed-out");
        return;
      }
      setErrorMessage(err instanceof ApiError ? err.message : "Couldn't save the card — try again.");
    } finally {
      setCreating(false);
    }
  }

  if (status === "loading") {
    return (
      <main className="proposal">
        <p className="muted">Getting a proposal from Nemo Anki…</p>
      </main>
    );
  }

  if (status === "record") {
    return (
      <main className="proposal">
        <h1>Add to Nemo Anki</h1>
        <p className="muted">
          {recording ? "Recording… speak a word or sentence." : "Tap record, then speak a word or sentence."}
        </p>
        {errorMessage && <p className="error">{errorMessage}</p>}
        <div className="actions">
          <button type="button" className="secondary" onClick={() => window.close()}>
            Cancel
          </button>
          {recording ? (
            <button type="button" onClick={handleStopRecording}>
              ⏹ Stop
            </button>
          ) : (
            <button type="button" onClick={() => void handleStartRecording()}>
              🎤 Record
            </button>
          )}
        </div>
      </main>
    );
  }

  if (status === "transcribing") {
    return (
      <main className="proposal">
        <p className="muted">🎤 Listening to what you said…</p>
      </main>
    );
  }

  if (status === "signed-out") {
    return (
      <main className="proposal">
        <p>Sign in to Nemo Anki first — click the toolbar icon, then try again.</p>
        <div className="actions">
          <button type="button" onClick={() => window.close()}>
            Close
          </button>
        </div>
      </main>
    );
  }

  if (status === "no-decks") {
    return (
      <main className="proposal">
        <p>You don&apos;t have any decks yet — create one in the Nemo Anki web app first.</p>
        <div className="actions">
          <button type="button" onClick={() => window.close()}>
            Close
          </button>
        </div>
      </main>
    );
  }

  if (status === "error") {
    return (
      <main className="proposal">
        <p className="error">{errorMessage}</p>
        <div className="actions">
          <button type="button" onClick={() => window.close()}>
            Close
          </button>
        </div>
      </main>
    );
  }

  if (created) {
    return (
      <main className="proposal">
        <p>Card created ✓{imageAttachFailed ? " — image couldn't be attached" : ""}</p>
      </main>
    );
  }

  return (
    <main className="proposal">
      <h1>Add to Nemo Anki</h1>
      {mode === "voice" && front && <p className="muted">🎤 I heard: "{front}"</p>}
      {mode === "image" && imageDataUrl && (
        <>
          <img src={imageDataUrl} alt="" className="image-preview" />
          <p className="muted">
            {front
              ? `🖼️ I read: "${front}"`
              : "🖼️ Couldn't read any text in this image — fill in the card yourself."}
          </p>
        </>
      )}

      <div className="toggle">
        <button
          type="button"
          className={category === "word" ? "active" : ""}
          onClick={() => setCategory("word")}
        >
          Word
        </button>
        <button
          type="button"
          className={category === "sentence" ? "active" : ""}
          onClick={() => setCategory("sentence")}
        >
          Sentence
        </button>
      </div>

      <label>
        Front
        <textarea value={front} onChange={(e) => setFront(e.target.value)} rows={2} />
      </label>
      <label>
        Back
        <textarea value={back} onChange={(e) => setBack(e.target.value)} rows={2} />
      </label>
      <label>
        Reading
        <input type="text" value={reading} onChange={(e) => setReading(e.target.value)} />
      </label>
      <label>
        Example
        <textarea value={example} onChange={(e) => setExample(e.target.value)} rows={2} />
      </label>
      <label>
        Deck
        <select value={deckId ?? ""} onChange={(e) => setDeckId(Number(e.target.value))}>
          {decks.map((d) => (
            <option key={d.id} value={d.id}>
              {d.full_name}
            </option>
          ))}
        </select>
      </label>

      {errorMessage && <p className="error">{errorMessage}</p>}

      <div className="actions">
        <button type="button" className="secondary" onClick={() => window.close()}>
          Cancel
        </button>
        <button type="button" onClick={() => void handleCreate()} disabled={creating || !deckId}>
          {creating ? "Creating…" : "Create Card"}
        </button>
      </div>
    </main>
  );
}
