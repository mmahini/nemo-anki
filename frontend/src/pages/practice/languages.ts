/** Languages the practice tabs share. One list, so the target language you pick
 * carries across writing, speaking and reading aloud. */
export type PracticeLang = {
  code: string;
  name: string;
  /** BCP-47 tag for speech synthesis + recognition. */
  speech: string;
};

export const LANGS: PracticeLang[] = [
  { code: "de", name: "German", speech: "de-DE" },
  { code: "en", name: "English", speech: "en-US" },
  { code: "fr", name: "French", speech: "fr-FR" },
  { code: "es", name: "Spanish", speech: "es-ES" },
  { code: "it", name: "Italian", speech: "it-IT" },
];

export function findLang(code: string): PracticeLang {
  return LANGS.find((l) => l.code === code) ?? LANGS[0];
}

/** The learner's own language — what writing prompts get shown in. */
export const NATIVE_LANGS = [
  { code: "English", label: "English" },
  { code: "Persian", label: "Persian / فارسی" },
  { code: "French", label: "French / Français" },
  { code: "Spanish", label: "Spanish / Español" },
  { code: "Italian", label: "Italian / Italiano" },
  { code: "Arabic", label: "Arabic / العربية" },
  { code: "Russian", label: "Russian / Русский" },
  { code: "Chinese", label: "Chinese / 中文" },
  { code: "Turkish", label: "Turkish / Türkçe" },
];

/** Read-aloud passages used when the AI text call fails, so the tab still works
 * offline-ish rather than dead-ending. */
const FALLBACK_TEXTS: Record<string, string[]> = {
  de: [
    "Heute Morgen bin ich früh aufgestanden. Nach dem Frühstück bin ich zur Arbeit gegangen. Am Abend habe ich mit einem Freund Kaffee getrunken.",
    "Das Wetter ist heute sehr schön. Ich gehe gerne in den Park und lese ein Buch. Die Vögel singen und die Sonne scheint hell.",
    "Letzte Woche habe ich einen neuen Film gesehen. Die Geschichte war sehr interessant. Ich empfehle ihn allen meinen Freunden.",
    "Jeden Morgen trinke ich eine Tasse Kaffee und lese die Nachrichten. Dann fahre ich mit dem Fahrrad zur Arbeit. Der Weg dauert ungefähr zwanzig Minuten.",
    "Am Wochenende bin ich mit meiner Familie in die Berge gefahren. Wir haben gewandert und frische Luft genossen. Abends haben wir in einer kleinen Hütte gegessen.",
    "Mein Lieblingsrestaurant liegt in der Nähe des Bahnhofs. Das Essen dort ist immer frisch und lecker. Ich gehe oft mit meinen Kollegen dorthin.",
  ],
  en: [
    "This morning I woke up early. After breakfast, I went to work. In the evening, I had coffee with a friend.",
    "The weather is beautiful today. I like going to the park and reading a book. The birds are singing and the sun is shining.",
    "Last week I watched a new film. The story was very interesting. I recommend it to all my friends.",
    "Every morning I drink a cup of coffee and read the news. Then I cycle to work. The journey takes about twenty minutes.",
    "Last weekend I went hiking with my family. We enjoyed the fresh air and beautiful views. In the evening we had dinner at a small restaurant.",
  ],
  fr: [
    "Ce matin, je me suis réveillé tôt. Après le petit-déjeuner, je suis allé au travail. Le soir, j'ai pris un café avec un ami.",
    "Le temps est très beau aujourd'hui. J'aime me promener dans le parc et lire un livre. Les oiseaux chantent et le soleil brille.",
    "La semaine dernière, j'ai commencé à apprendre une nouvelle recette. J'ai fait une soupe de légumes simple mais délicieuse.",
  ],
  es: [
    "Esta mañana me desperté temprano. Después del desayuno, fui al trabajo. Por la tarde, tomé un café con un amigo.",
    "El tiempo está muy bonito hoy. Me gusta ir al parque y leer un libro. Los pájaros cantan y el sol brilla.",
    "El fin de semana pasado fui de excursión con mi familia. Disfrutamos del aire fresco y las vistas. Por la noche cenamos en un pequeño restaurante.",
  ],
  it: [
    "Stamattina mi sono svegliato presto. Dopo colazione, sono andato al lavoro. La sera, ho preso un caffè con un amico.",
    "Il tempo è molto bello oggi. Mi piace andare al parco e leggere un libro. Gli uccelli cantano e il sole splende.",
    "Il fine settimana scorso sono andato in montagna con la mia famiglia. Abbiamo fatto escursioni e respirato aria fresca.",
  ],
};

export function randomFallback(langCode: string): string {
  const pool = FALLBACK_TEXTS[langCode] ?? FALLBACK_TEXTS.en;
  return pool[Math.floor(Math.random() * pool.length)];
}
