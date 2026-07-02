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
 */

const GOOGLE_TTS_MAX = 200;

export function canSpeak(): boolean {
  return typeof window !== "undefined" && (typeof Audio !== "undefined" || "speechSynthesis" in window);
}

function hasWebSpeech(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

function bcp47(lang: string): string {
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

function stopAll(): void {
  playToken += 1;
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.src = "";
    currentAudio = null;
  }
  if (hasWebSpeech()) window.speechSynthesis.cancel();
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

function webSpeak(text: string, lang: string): void {
  if (!hasWebSpeech() || !text.trim()) return;
  const u = new SpeechSynthesisUtterance(text);
  const tag = bcp47(lang);
  if (tag) u.lang = tag;
  const voice = pickVoice(lang);
  if (voice) u.voice = voice;
  u.rate = 0.95;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(u);
}

export function speak(text: string, lang: string): void {
  text = (text || "").trim();
  if (!canSpeak() || !text) return;
  stopAll();

  const tl = ttsLang(lang);
  const chunks = tl ? chunk(text) : [];
  if (!chunks.length) {
    webSpeak(text, lang);
    return;
  }

  const token = playToken;
  let i = 0;
  const playNext = () => {
    if (token !== playToken) return; // superseded by a newer speak()
    if (i >= chunks.length) {
      currentAudio = null;
      return;
    }
    const audio = new Audio(googleTtsUrl(chunks[i], tl));
    currentAudio = audio;
    audio.onended = () => {
      i += 1;
      playNext();
    };
    const onFail = () => {
      if (token !== playToken) return;
      currentAudio = null;
      // Google unreachable — read the remaining text via the browser voice.
      webSpeak(chunks.slice(i).join(" "), lang);
    };
    audio.onerror = onFail;
    audio.play().catch(onFail);
  };
  playNext();
}
