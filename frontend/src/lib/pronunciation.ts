/** Pronunciation check: record one utterance via the browser's Web Speech
 * API (SpeechRecognition) and fuzzy-match it against the expected text.
 * Client-side only — no backend, no key. Chrome/Edge only (Firefox/Safari
 * don't ship SpeechRecognition), so callers must gate on `sttSupported()`. */

import { setActiveListener } from "./audioLock";
import { bcp47 } from "./tts";

function speechRecognitionCtor(): SpeechRecognitionConstructor | undefined {
  if (typeof window === "undefined") return undefined;
  return window.SpeechRecognition ?? window.webkitSpeechRecognition;
}

export function sttSupported(): boolean {
  return !!speechRecognitionCtor();
}

/** Listen for a single utterance and resolve with the recognised transcript.
 * Rejects if unsupported, denied, or nothing was heard. */
export function listenOnce(lang: string): Promise<string> {
  const Ctor = speechRecognitionCtor();
  if (!Ctor) return Promise.reject(new Error("Speech recognition is not supported in this browser."));

  return new Promise((resolve, reject) => {
    const recognition = new Ctor();
    recognition.lang = bcp47(lang) || "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    let settled = false;

    recognition.onresult = (e) => {
      settled = true;
      setActiveListener(null);
      resolve(e.results[0]?.[0]?.transcript ?? "");
    };
    recognition.onerror = (e) => {
      if (settled) return;
      settled = true;
      setActiveListener(null);
      reject(new Error(e.error || "speech-recognition-error"));
    };
    recognition.onend = () => {
      if (!settled) {
        settled = true;
        setActiveListener(null);
        reject(new Error("no-speech"));
      }
    };
    setActiveListener(() => recognition.abort());
    recognition.start();
  });
}

const LEADING_ARTICLES = new Set([
  "der", "die", "das", "den", "dem", "des",
  "ein", "eine", "einen", "einem", "einer", "eines",
  "the", "a", "an",
]);

function normalize(s: string): string {
  return s
    .toLowerCase()
    .replace(/[.,!?;:„"“”'’()\-]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Learners naturally say a German noun with its article ("der Name"), but
 * `front` never includes one — drop a leading article before comparing. */
function stripLeadingArticle(s: string): string {
  const words = s.split(" ");
  return words.length > 1 && LEADING_ARTICLES.has(words[0]) ? words.slice(1).join(" ") : s;
}

function levenshtein(a: string, b: string): number {
  if (!a.length) return b.length;
  if (!b.length) return a.length;
  const dp = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    let prevDiag = dp[0];
    dp[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const tmp = dp[j];
      dp[j] = a[i - 1] === b[j - 1] ? prevDiag : 1 + Math.min(prevDiag, dp[j], dp[j - 1]);
      prevDiag = tmp;
    }
  }
  return dp[b.length];
}

/** Fuzzy-compares heard speech against the expected text, tolerant of small
 * recognition slips (a wrong ending, a missed umlaut) via edit distance. */
export function isPronunciationMatch(expected: string, heard: string): boolean {
  const exp = normalize(expected);
  const hrd = stripLeadingArticle(normalize(heard));
  if (!exp || !hrd) return false;
  if (exp === hrd) return true;
  const threshold = Math.max(1, Math.floor(exp.length * 0.25));
  return levenshtein(exp, hrd) <= threshold;
}
