/** Text-to-speech.
 *
 * Primary path: play Google Translate's own TTS audio (the same natural voice
 * you hear in Google Translate) via its `translate_tts` endpoint. Media
 * playback isn't subject to CORS, so an <audio> element can stream the MP3
 * cross-origin — no backend, no key. The endpoint caps each request at ~200
 * chars, so longer / multi-line text is split into chunks played back-to-back.
 *
 * Fallback: if Google is unreachable (offline / throttled / blocked), degrade
 * to the browser's Web Speech API, preferring a Google-branded voice if the
 * browser exposes one (Chrome ships "Google Deutsch" etc.).
 *
 * iOS is the awkward platform here and drives three details below:
 *  - `speechSynthesis.speak()` is dropped unless the synthesiser has been
 *    started from inside a user gesture at least once. The fallback runs from
 *    an async error callback, long after the gesture, so it has to be primed
 *    up front — see primeWebSpeech.
 *  - a media element may only play outside a gesture once it has played inside
 *    one, so every chunk reuses a single element rather than making a new one.
 *  - when both paths stay silent there is nothing to catch, so playback is
 *    watched and SPEECH_FAILED_EVENT is fired for SpeechHelp to explain.
 */

import { stopActiveListening } from "./audioLock";

const GOOGLE_TTS_MAX = 200;

/** How long to give a path to actually start making sound before treating it
 * as failed. iOS can accept an utterance and then never fire any event. */
const SPEECH_START_TIMEOUT_MS = 1500;

/** Fired on window when a 🔊 press produced no audible speech at all — both
 * the Google audio path and the browser voice failed or stayed silent. */
export const SPEECH_FAILED_EVENT = "nemo:speech-failed";

/** iPhone/iPad, including iPadOS which reports itself as a Mac. */
export function isIOS(): boolean {
  if (typeof navigator === "undefined") return false;
  return (
    /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.userAgent.includes("Mac") && typeof document !== "undefined" && "ontouchend" in document)
  );
}

/** Running as an installed/home-screen app rather than a browser tab. */
export function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia?.("(display-mode: standalone)").matches ||
    (navigator as unknown as { standalone?: boolean }).standalone === true
  );
}

export function canSpeak(): boolean {
  return typeof window !== "undefined" && (typeof Audio !== "undefined" || "speechSynthesis" in window);
}

function hasWebSpeech(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

/** BCP-47 language tag for Web Speech APIs (both synthesis and recognition). */
export function bcp47(lang: string): string {
  if (lang === "de") return "de-DE";
  if (lang === "en") return "en-US";
  return "";
}

/** Language code for Google Translate TTS (`tl` param). */
function ttsLang(lang: string): string {
  if (lang === "de") return "de";
  if (lang === "en") return "en";
  return lang || "";
}

function googleTtsUrl(text: string, tl: string): string {
  const q = encodeURIComponent(text);
  return `https://translate.google.com/translate_tts?ie=UTF-8&tl=${encodeURIComponent(tl)}&client=tw-ob&q=${q}`;
}

/** Break text into <=200-char pieces, splitting on lines/sentences/spaces so a
 * chunk never cuts mid-word. */
function chunk(text: string, max = GOOGLE_TTS_MAX): string[] {
  const out: string[] = [];
  for (const line of text.split(/\n+/)) {
    let rest = line.trim();
    while (rest.length > max) {
      // Prefer a sentence/clause break in the back half; else the last space.
      let cut = -1;
      for (const p of [". ", "! ", "? ", "; ", ", "]) {
        cut = Math.max(cut, rest.lastIndexOf(p, max) + 1);
      }
      if (cut < max * 0.5) cut = rest.lastIndexOf(" ", max);
      if (cut <= 0) cut = max;
      out.push(rest.slice(0, cut).trim());
      rest = rest.slice(cut).trim();
    }
    if (rest) out.push(rest);
  }
  return out;
}

// A monotonically increasing token lets a new speak() cancel an in-flight one.
let currentAudio: HTMLAudioElement | null = null;
let playToken = 0;

/** The one media element every chunk plays through. iOS only lets an element
 * play outside a user gesture once that same element has played inside one, so
 * a fresh Audio per chunk goes silent after the first chunk on iPhone. */
let sharedAudio: HTMLAudioElement | null = null;

function getAudio(): HTMLAudioElement {
  if (!sharedAudio) {
    sharedAudio = new Audio();
    sharedAudio.preload = "auto";
  }
  return sharedAudio;
}

/** Stop any in-flight speak() playback — call before starting the mic so the
 * pronunciation check can't hear the TTS's own voice through the speakers. */
export function stopSpeaking(): void {
  stopAll();
}

function stopAll(): void {
  playToken += 1;
  if (currentAudio) {
    // Detach the handlers so nothing from the old playback reaches the
    // fallback, then just pause. The source is deliberately left alone —
    // clearing it fires a spurious error event on the shared element, and the
    // next speak() overwrites it anyway.
    currentAudio.onended = null;
    currentAudio.onerror = null;
    currentAudio.pause();
    currentAudio = null;
  }
  if (hasWebSpeech()) window.speechSynthesis.cancel();
}

/** Unlock the speech synthesiser while we still have the user gesture.
 *
 * Without this, iOS silently discards the fallback utterance further down —
 * it is issued from an async error handler — so a 🔊 press whose Google
 * request fails makes no sound whatsoever and reports nothing. */
let webSpeechPrimed = false;

function primeWebSpeech(): void {
  if (webSpeechPrimed || !hasWebSpeech()) return;
  webSpeechPrimed = true;
  try {
    const u = new SpeechSynthesisUtterance(" ");
    u.volume = 0;
    window.speechSynthesis.speak(u);
  } catch {
    // Best-effort: a browser that refuses this still works on the normal path.
  }
}

function reportFailure(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(SPEECH_FAILED_EVENT));
  }
}

/** Pick a matching-language voice, preferring a Google one (Web Speech fallback). */
function pickVoice(lang: string): SpeechSynthesisVoice | undefined {
  const want = bcp47(lang).toLowerCase().slice(0, 2);
  if (!want) return undefined;
  const matches = window.speechSynthesis
    .getVoices()
    .filter((v) => v.lang.toLowerCase().startsWith(want));
  return matches.find((v) => /google/i.test(v.name)) ?? matches[0];
}

/** Speak with the browser's own voice. Resolves true only once the synthesiser
 * has actually started — iOS will happily accept an utterance and then never
 * fire anything, which is indistinguishable from success without the timeout. */
function webSpeak(text: string, lang: string): Promise<boolean> {
  return new Promise((resolve) => {
    if (!hasWebSpeech() || !text.trim()) {
      resolve(false);
      return;
    }
    const u = new SpeechSynthesisUtterance(text);
    const tag = bcp47(lang);
    if (tag) u.lang = tag;
    const voice = pickVoice(lang);
    if (voice) u.voice = voice;
    u.rate = 0.95;

    let settled = false;
    const done = (ok: boolean) => {
      if (settled) return;
      settled = true;
      resolve(ok);
    };
    u.onstart = () => done(true);
    u.onerror = () => done(false);
    // No cancel() here: on iOS a cancel() immediately before speak() drops the
    // new utterance. stopAll() has already cleared anything in flight.
    window.speechSynthesis.speak(u);
    window.setTimeout(() => done(false), SPEECH_START_TIMEOUT_MS);
  });
}

/** The last thing asked for, so the "try again" button in SpeechHelp can retry
 * it from a fresh user gesture — which is often all iOS needs. */
let lastSpoken: { text: string; lang: string } | null = null;

export function retryLastSpeak(): void {
  if (lastSpoken) speak(lastSpoken.text, lastSpoken.lang);
}

type SpeakOptions = {
  /** Playback the user didn't ask for — auto-reading a card as it appears.
   * iOS blocks audio outside a user gesture as a matter of course, so this
   * failing is normal and must not raise the "no sound came out" panel. */
  auto?: boolean;
};

export function speak(text: string, lang: string, opts: SpeakOptions = {}): void {
  text = (text || "").trim();
  if (!canSpeak() || !text) return;
  stopActiveListening(); // don't let an open mic hear this playback and misjudge it
  stopAll();
  // Only a real press carries a gesture worth spending on the synthesiser.
  if (!opts.auto) primeWebSpeech();
  lastSpoken = { text, lang };
  const report = () => {
    if (!opts.auto) reportFailure();
  };

  const tl = ttsLang(lang);
  const chunks = tl ? chunk(text) : [];
  if (!chunks.length) {
    webSpeak(text, lang).then((ok) => {
      if (!ok) report();
    });
    return;
  }

  const token = playToken;
  let i = 0;
  // A failed load fires BOTH the element's error event and a rejection from
  // play(), so without this latch the fallback runs twice and the text is read
  // out twice over.
  let failed = false;
  const onFail = () => {
    if (token !== playToken || failed) return;
    failed = true;
    // Silence the element before handing over. play() can reject while the
    // element still goes on to produce sound, and then both voices would talk
    // over each other.
    const stale = currentAudio;
    currentAudio = null;
    if (stale) {
      stale.onended = null;
      stale.onerror = null;
      stale.pause();
    }
    // Google unreachable — read the remaining text via the browser voice, and
    // speak up if that makes no sound either.
    webSpeak(chunks.slice(i).join(" "), lang).then((ok) => {
      if (!ok && token === playToken) report();
    });
  };
  const playNext = () => {
    if (token !== playToken) return; // superseded by a newer speak()
    if (i >= chunks.length) {
      currentAudio = null;
      return;
    }
    const audio = getAudio();
    currentAudio = audio;
    audio.onended = () => {
      i += 1;
      playNext();
    };
    audio.onerror = onFail;
    audio.src = googleTtsUrl(chunks[i], tl);
    audio.play().catch(onFail);
  };
  playNext();
}
