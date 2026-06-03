/** Text-to-speech via the browser's Web Speech API (no backend / no key). */

export function canSpeak(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

function bcp47(lang: string): string {
  if (lang === "de") return "de-DE";
  if (lang === "en") return "en-US";
  return "";
}

/** Pick a voice matching the language if one is installed. */
function pickVoice(lang: string): SpeechSynthesisVoice | undefined {
  const want = bcp47(lang).toLowerCase().slice(0, 2);
  if (!want) return undefined;
  return window.speechSynthesis
    .getVoices()
    .find((v) => v.lang.toLowerCase().startsWith(want));
}

export function speak(text: string, lang: string): void {
  if (!canSpeak() || !text.trim()) return;
  const u = new SpeechSynthesisUtterance(text);
  const tag = bcp47(lang);
  if (tag) u.lang = tag;
  const voice = pickVoice(lang);
  if (voice) u.voice = voice;
  u.rate = 0.95;
  window.speechSynthesis.cancel(); // stop anything already playing
  window.speechSynthesis.speak(u);
}
