/** Short success/failure feedback sounds for the pronunciation check. */

/** A bright chime for a correct pronunciation. */
export function playCorrectSound(): void {
  new Audio("/sounds/success-chime.mp3").play().catch(() => {});
}

/** A short buzz for an incorrect pronunciation, cut off at 1s. */
export function playWrongSound(): void {
  const audio = new Audio("/sounds/fail-sound.mp3");
  audio.play().catch(() => {});
  setTimeout(() => {
    audio.pause();
    audio.currentTime = 0;
  }, 1000);
}
