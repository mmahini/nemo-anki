import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Browser speech recognition + synthesis for the speaking tabs.
 *
 * Both the chat and read-aloud tabs need the same three things — is speech
 * available, say this, listen for one utterance — so they share this instead of
 * each keeping its own recogniser. Crucially it also *tears down* on unmount:
 * leaving the page mid-sentence used to leave the synthesiser talking and the
 * microphone live.
 */
export function useSpeech(speechLang: string) {
  const [listening, setListening] = useState(false);
  const recRef = useRef<any>(null);

  const supported =
    typeof window !== "undefined" &&
    ("SpeechRecognition" in window || "webkitSpeechRecognition" in window);

  const speak = useCallback(
    (text: string) => {
      if (typeof window === "undefined" || !window.speechSynthesis) return;
      window.speechSynthesis.cancel();
      const utt = new SpeechSynthesisUtterance(text);
      utt.lang = speechLang;
      utt.rate = 0.9;
      window.speechSynthesis.speak(utt);
    },
    [speechLang],
  );

  const stop = useCallback(() => {
    recRef.current?.stop?.();
    setListening(false);
  }, []);

  const listen = useCallback(
    (onResult: (transcript: string) => void) => {
      const SpeechRec =
        (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      if (!SpeechRec) return;
      const rec = new SpeechRec();
      rec.lang = speechLang;
      rec.interimResults = false;
      rec.maxAlternatives = 1;
      recRef.current = rec;
      rec.onresult = (e: any) => onResult(e.results[0][0].transcript);
      rec.onend = () => setListening(false);
      rec.onerror = () => setListening(false);
      rec.start();
      setListening(true);
    },
    [speechLang],
  );

  /** Start listening, or stop if already listening. */
  const toggle = useCallback(
    (onResult: (transcript: string) => void) => {
      if (listening) stop();
      else listen(onResult);
    },
    [listening, listen, stop],
  );

  useEffect(() => {
    return () => {
      recRef.current?.abort?.();
      if (typeof window !== "undefined") window.speechSynthesis?.cancel();
    };
  }, []);

  return { supported, listening, speak, listen, stop, toggle };
}
