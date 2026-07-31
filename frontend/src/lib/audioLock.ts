/** Tiny coordination point between TTS playback and speech-recognition
 * listening, so one can't run while the other is active — otherwise the mic
 * hears the 🔊 button's own voice through the speakers and misjudges it as
 * a (correct or incorrect) attempt the user never actually spoke. */

let stopListening: (() => void) | null = null;

/** Registered by pronunciation.ts while a recognition session is open. */
export function setActiveListener(stop: (() => void) | null): void {
  stopListening = stop;
}

/** Abort any in-progress speech-recognition session — call before playing TTS. */
export function stopActiveListening(): void {
  stopListening?.();
  stopListening = null;
}
