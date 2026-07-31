"""Generate an original Reading + Listening placement test with Gemini.

Never reproduces real IELTS/TOEFL/etc. questions — every question is freshly
generated in the *style* of a standardized test (short passage + multiple
choice), tagged with the CEFR level it targets. Falls back to a small
hand-written question pool when GEMINI_API_KEY is unset or the call fails, so
the feature still works offline/in dev (same pattern as apps.imports.gemini).
"""
from __future__ import annotations

import json
import random
import re

import requests
from django.conf import settings

from .models import LEVELS

_LANG_NAMES = {"de": "German", "en": "English"}

# quick = 1 reading + 1 listening per level (10 total); full = 2 + 2 (20 total).
PER_LEVEL_BY_LENGTH = {"quick": 1, "full": 2}

_PROMPT = """You are creating an ORIGINAL placement test for a {language_name} \
learner, in the style of standardized tests like IELTS/TOEFL — but every \
question must be 100% original content that you write yourself. NEVER copy or \
paraphrase real exam questions.

Generate exactly {per_level} READING and {per_level} LISTENING multiple-choice \
questions for EACH of these CEFR levels: A1, A2, B1, B2, C1 (so {total} \
questions total). Vary vocabulary and grammar so difficulty genuinely matches \
each level — A1 is the simplest, C1 is the most advanced.

Return ONLY a JSON array of {total} objects, each with these keys:
- "level": one of "A1","A2","B1","B2","C1".
- "section": "reading" or "listening".
- "text": a short original passage in {language_name} (2-4 sentences, level-\
appropriate). For "listening" this is meant to be heard, not read, so keep \
sentences simple enough to follow by ear.
- "question": a comprehension question about "text", written in {language_name}.
- "choices": an array of exactly 4 answer options in {language_name}.
- "correct_index": the 0-based index of the correct option in "choices".

Make exactly one option clearly correct per question. Output strictly valid \
JSON, no markdown fences, no commentary.
"""


def generate_placement_questions(language: str, length: str) -> list[dict]:
    """Return a flat list of question dicts:
    ``{"level","section","text","question","choices","correct_index"}``.
    Always returns the right count (pads from the fallback pool if Gemini
    under-delivers or is unavailable)."""
    per_level = PER_LEVEL_BY_LENGTH.get(length, 1)
    total = per_level * len(LEVELS) * 2

    generated: list[dict] = []
    if settings.GEMINI_API_KEY:
        try:
            generated = _generate_with_gemini(language, per_level, total)
        except Exception:  # noqa: BLE001 — degrade to the fallback pool below
            generated = []

    return _fill_to_count(generated, language, per_level, total)


def _generate_with_gemini(language: str, per_level: int, total: int) -> list[dict]:
    prompt = _PROMPT.format(
        language_name=_LANG_NAMES.get(language, "the target language"),
        per_level=per_level,
        total=total,
    )
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "responseMimeType": "application/json"},
    }
    verify = getattr(settings, "GEMINI_VERIFY_SSL", True)
    res = requests.post(url, json=payload, timeout=60, verify=verify)
    res.raise_for_status()
    raw = res.json()["candidates"][0]["content"]["parts"][0]["text"]
    return [q for item in _extract_json_array(raw) if (q := _normalise(item))]


def _extract_json_array(raw: str) -> list:
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        val = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", raw, flags=re.DOTALL)
        if not match:
            return []
        val = json.loads(match.group(0))
    return val if isinstance(val, list) else []


def _normalise(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    level = item.get("level")
    section = item.get("section")
    choices = item.get("choices")
    text = str(item.get("text", "")).strip()
    question = str(item.get("question", "")).strip()
    try:
        correct_index = int(item.get("correct_index"))
    except (TypeError, ValueError):
        return None
    if (
        level not in LEVELS
        or section not in ("reading", "listening")
        or not isinstance(choices, list)
        or len(choices) != 4
        or not text
        or not question
        or not (0 <= correct_index < 4)
    ):
        return None
    return {
        "level": level,
        "section": section,
        "text": text,
        "question": question,
        "choices": [str(c).strip() for c in choices],
        "correct_index": correct_index,
    }


def _fill_to_count(generated: list[dict], language: str, per_level: int, total: int) -> list[dict]:
    """Group what Gemini gave us by (level, section) and top up any short
    slots with a random, non-repeating draw from the fallback bank (only
    repeating a question if the bank is smaller than what's needed)."""
    pool = _FALLBACK.get(language, _FALLBACK["en"])
    by_slot: dict[tuple[str, str], list[dict]] = {}
    for q in generated:
        by_slot.setdefault((q["level"], q["section"]), []).append(q)

    out: list[dict] = []
    for level in LEVELS:
        for section in ("reading", "listening"):
            have = by_slot.get((level, section), [])
            need = per_level - len(have)
            if need > 0:
                fallback_pool = pool.get((level, section), [])
                if fallback_pool:
                    if need <= len(fallback_pool):
                        have = have + random.sample(fallback_pool, need)
                    else:
                        shuffled = random.sample(fallback_pool, len(fallback_pool))
                        while len(shuffled) < need:
                            shuffled.append(random.choice(fallback_pool))
                        have = have + shuffled[:need]
            out.extend(have[:per_level])
    return out[:total] if len(out) > total else out


# One original, hand-written fallback question per (level, section) per
# language — used when GEMINI_API_KEY is unset or the call fails. Cycled to
# fill "full" mode (2 per level) if needed.
_FALLBACK: dict[str, dict[tuple[str, str], list[dict]]] = {
    "en": {
        ("A1", "reading"): [{
            "level": "A1", "section": "reading",
            "text": "My name is Anna. I am ten years old. I have a small dog. His name is Max.",
            "question": "What is the name of Anna's dog?",
            "choices": ["Anna", "Max", "Ten", "Small"], "correct_index": 1,
        }, {
            "level": "A1", "section": "reading",
            "text": "This is my family. My mother is a teacher. My father is a doctor. I have one brother.",
            "question": "What is the mother's job?",
            "choices": ["Doctor", "Teacher", "Nurse", "Student"], "correct_index": 1,
        }, {
            "level": "A1", "section": "reading",
            "text": "Today is Monday. I go to school every day. My school is near my house. I like my school.",
            "question": "Where is the school?",
            "choices": ["Far away", "Near the house", "In another city", "Next to the market"], "correct_index": 1,
        }, {
            "level": "A1", "section": "reading",
            "text": "I have a cat. Her name is Lily. She is black and white. She likes to sleep.",
            "question": "What color is Lily?",
            "choices": ["Black and white", "Brown", "Orange", "Grey"], "correct_index": 0,
        }],
        ("A1", "listening"): [{
            "level": "A1", "section": "listening",
            "text": "This is a red apple. It is on the table. I like apples.",
            "question": "What color is the apple?",
            "choices": ["Green", "Yellow", "Red", "Blue"], "correct_index": 2,
        }, {
            "level": "A1", "section": "listening",
            "text": "Hello! My name is Sam. I am from Canada. I speak English and French.",
            "question": "Where is Sam from?",
            "choices": ["France", "Canada", "Germany", "Spain"], "correct_index": 1,
        }, {
            "level": "A1", "section": "listening",
            "text": "It is nine o'clock. The children are eating breakfast. They eat bread and milk.",
            "question": "What are the children eating?",
            "choices": ["Bread and milk", "Rice", "Soup", "Fruit"], "correct_index": 0,
        }, {
            "level": "A1", "section": "listening",
            "text": "This is my room. There is a bed and a table. My books are on the table.",
            "question": "Where are the books?",
            "choices": ["On the bed", "On the table", "On the floor", "In the bag"], "correct_index": 1,
        }],
        ("A2", "reading"): [{
            "level": "A2", "section": "reading",
            "text": "Every Saturday, Tom goes to the market with his mother. They buy fruit, "
                     "vegetables, and sometimes fresh bread. Tom likes choosing the apples himself.",
            "question": "When does Tom go to the market?",
            "choices": ["Every day", "Every Saturday", "Every Sunday", "Never"], "correct_index": 1,
        }, {
            "level": "A2", "section": "reading",
            "text": "Maria works in a small shop in the city center. She opens the shop at eight and "
                     "closes it at six. On Sundays the shop is closed.",
            "question": "When is the shop closed?",
            "choices": ["Every evening", "On Sundays", "On Saturdays", "Never"], "correct_index": 1,
        }, {
            "level": "A2", "section": "reading",
            "text": "Last weekend, Ali and his friends went camping near the lake. They swam, cooked "
                     "dinner outside, and told stories at night.",
            "question": "Where did Ali go camping?",
            "choices": ["In the mountains", "Near the lake", "At the beach", "In the forest"], "correct_index": 1,
        }, {
            "level": "A2", "section": "reading",
            "text": "My sister is learning to cook. Yesterday she made a chicken soup, but she forgot "
                     "to add salt, so it tasted a bit strange.",
            "question": "What was wrong with the soup?",
            "choices": ["It was too salty", "It had no salt", "It was too spicy", "It was cold"], "correct_index": 1,
        }],
        ("A2", "listening"): [{
            "level": "A2", "section": "listening",
            "text": "Yesterday it rained all day, so we stayed home and watched a film. "
                     "Today the sun is out, so we are going for a walk in the park.",
            "question": "What are they doing today?",
            "choices": ["Watching a film", "Staying home", "Going for a walk", "Waiting for rain"],
            "correct_index": 2,
        }, {
            "level": "A2", "section": "listening",
            "text": "We are planning our summer holiday. My parents want to visit the mountains, but "
                     "I would rather go to the beach and swim every day.",
            "question": "What does the speaker want to do?",
            "choices": ["Visit the mountains", "Go to the beach", "Stay home", "Visit a city"], "correct_index": 1,
        }, {
            "level": "A2", "section": "listening",
            "text": "The bus was late this morning, so I missed my first class. My teacher was not "
                     "happy, but she let me stay.",
            "question": "Why did the speaker miss class?",
            "choices": ["They woke up late", "The bus was late", "They were sick", "They forgot the time"],
            "correct_index": 1,
        }, {
            "level": "A2", "section": "listening",
            "text": "On Fridays, our family always eats dinner together and watches a movie afterward. "
                     "It is my favorite day of the week.",
            "question": "What do they do after dinner on Fridays?",
            "choices": ["Go for a walk", "Watch a movie", "Play games", "Go to bed early"], "correct_index": 1,
        }],
        ("B1", "reading"): [{
            "level": "B1", "section": "reading",
            "text": "Although the small bakery on Elm Street has no website and only opens until "
                     "noon, it has become one of the most popular spots in town, mostly because of "
                     "word-of-mouth recommendations from regular customers.",
            "question": "Why has the bakery become popular?",
            "choices": [
                "It has a very good website", "It stays open late", "People recommend it to others",
                "It recently moved to Elm Street",
            ], "correct_index": 2,
        }, {
            "level": "B1", "section": "reading",
            "text": "Public libraries used to be quiet places for reading, but many have changed in "
                     "recent years, now offering workshops, film nights, and even space for small "
                     "business meetings.",
            "question": "According to the passage, how have public libraries changed?",
            "choices": [
                "They closed down", "They now offer more activities", "They became more quiet",
                "They stopped lending books",
            ], "correct_index": 1,
        }, {
            "level": "B1", "section": "reading",
            "text": "When Elena moved to a new city for work, she knew nobody. She decided to join a "
                     "local sports club, which turned out to be the fastest way to make friends.",
            "question": "How did Elena make friends in the new city?",
            "choices": [
                "Through her job", "By joining a sports club", "Through her neighbors", "By staying home",
            ], "correct_index": 1,
        }, {
            "level": "B1", "section": "reading",
            "text": "Although the weather forecast predicted heavy rain, the outdoor concert went ahead "
                     "as planned, and luckily the rain held off until the very last song.",
            "question": "What happened during the concert?",
            "choices": [
                "It was cancelled because of rain", "It rained the whole time", "The rain came only at the end",
                "It was moved indoors",
            ], "correct_index": 2,
        }],
        ("B1", "listening"): [{
            "level": "B1", "section": "listening",
            "text": "I used to be afraid of public speaking, but after joining a local debate club "
                     "two years ago, I gradually became much more confident in front of an audience.",
            "question": "How did the speaker overcome their fear?",
            "choices": [
                "By avoiding public speaking", "By joining a debate club", "By reading books about it",
                "By speaking only to friends",
            ], "correct_index": 1,
        }, {
            "level": "B1", "section": "listening",
            "text": "I always found cooking boring until I started watching cooking shows during the "
                     "pandemic. Now I try a new recipe almost every weekend.",
            "question": "What changed the speaker's opinion about cooking?",
            "choices": [
                "A cooking class", "Watching cooking shows", "A friend's advice", "A cookbook",
            ], "correct_index": 1,
        }, {
            "level": "B1", "section": "listening",
            "text": "Our team missed the deadline because the client kept changing the requirements "
                     "halfway through the project, which forced us to redo a lot of work.",
            "question": "Why did the team miss the deadline?",
            "choices": [
                "They started too late", "The client kept changing requirements", "The team was too small",
                "The budget ran out",
            ], "correct_index": 1,
        }, {
            "level": "B1", "section": "listening",
            "text": "I used to commute by car, but the traffic got so bad that I switched to cycling, "
                     "and now I actually arrive at work faster.",
            "question": "Why did the speaker switch to cycling?",
            "choices": [
                "It was cheaper", "The traffic was bad", "Their car broke down", "For exercise only",
            ], "correct_index": 1,
        }],
        ("B2", "reading"): [{
            "level": "B2", "section": "reading",
            "text": "Critics have long argued that remote work erodes team cohesion, yet a growing "
                     "body of research suggests the opposite may be true when companies invest "
                     "deliberately in structured, recurring communication rather than leaving "
                     "collaboration to chance.",
            "question": "According to the passage, what determines whether remote work harms team cohesion?",
            "choices": [
                "Whether employees prefer working from home", "Whether communication is deliberately structured",
                "How many years the company has existed", "Whether critics agree with the research",
            ], "correct_index": 1,
        }, {
            "level": "B2", "section": "reading",
            "text": "Despite widespread assumptions that reading habits are declining, recent surveys "
                     "suggest that younger readers are simply migrating toward digital formats and "
                     "audiobooks rather than abandoning reading altogether.",
            "question": "What do the surveys suggest about younger readers?",
            "choices": [
                "They read less than before", "They are switching to digital formats",
                "They only listen to podcasts", "They prefer print books",
            ], "correct_index": 1,
        }, {
            "level": "B2", "section": "reading",
            "text": "The city council's decision to redesign the central square drew criticism from "
                     "local shopkeepers, who worried that reduced parking would drive customers away, "
                     "even though pedestrian traffic in similar redesigns elsewhere had increased "
                     "significantly.",
            "question": "Why were the shopkeepers concerned?",
            "choices": [
                "They disliked the new design", "They feared losing customers due to less parking",
                "They wanted more pedestrian traffic", "They opposed the council in general",
            ], "correct_index": 1,
        }, {
            "level": "B2", "section": "reading",
            "text": "It is tempting to credit a single visionary founder for a company's success, but "
                     "historical analysis usually reveals a far messier story involving timing, luck, "
                     "and the contributions of overlooked colleagues.",
            "question": "What does historical analysis usually reveal about company success?",
            "choices": [
                "A single founder's genius", "A combination of timing, luck, and teamwork",
                "Pure luck alone", "Careful long-term planning",
            ], "correct_index": 1,
        }],
        ("B2", "listening"): [{
            "level": "B2", "section": "listening",
            "text": "The committee postponed its decision, not because the proposal lacked merit, "
                     "but because two members felt the budget projections hadn't been stress-tested "
                     "against a slower economic recovery.",
            "question": "Why did the committee postpone its decision?",
            "choices": [
                "The proposal had no merit", "They wanted to test the budget against a slower recovery",
                "Two members resigned", "The budget was already approved",
            ], "correct_index": 1,
        }, {
            "level": "B2", "section": "listening",
            "text": "It's a common misconception that multitasking makes us more productive; in "
                     "reality, most studies show that switching between tasks constantly slows us "
                     "down and increases mistakes.",
            "question": "What do most studies show about multitasking?",
            "choices": [
                "It boosts productivity", "It slows us down and increases mistakes", "It has no effect",
                "It only works for simple tasks",
            ], "correct_index": 1,
        }, {
            "level": "B2", "section": "listening",
            "text": "The company delayed its product launch, not due to technical problems, but "
                     "because early customer feedback suggested the pricing model needed to be "
                     "reconsidered entirely.",
            "question": "Why was the launch delayed?",
            "choices": [
                "Technical problems", "Concerns about pricing", "Lack of customers", "Manufacturing delays",
            ], "correct_index": 1,
        }, {
            "level": "B2", "section": "listening",
            "text": "Many assume that working longer hours automatically leads to better results, but "
                     "the speaker argues that rest and recovery are just as critical to sustained "
                     "performance.",
            "question": "What does the speaker argue is just as important as working hours?",
            "choices": [
                "Rest and recovery", "Salary increases", "Team size", "Office location",
            ], "correct_index": 0,
        }],
        ("C1", "reading"): [{
            "level": "C1", "section": "reading",
            "text": "It would be reductive to attribute the sudden revival of interest in vinyl "
                     "records solely to nostalgia; for many younger collectors, the appeal lies "
                     "instead in the deliberate friction of the format — the ritual of handling, "
                     "the imposed patience — in an otherwise frictionless digital age.",
            "question": "What does the author suggest is the main appeal of vinyl for younger collectors?",
            "choices": [
                "Nostalgia for the past", "The deliberate, unhurried ritual of using the format",
                "Lower price compared to digital music", "Better sound quality than streaming",
            ], "correct_index": 1,
        }, {
            "level": "C1", "section": "reading",
            "text": "The resurgence of interest in analog photography cannot simply be dismissed as a "
                     "retro trend; for many practitioners, the deliberate constraints of film — "
                     "limited exposures, no instant preview — cultivate a discipline that digital "
                     "abundance tends to erode.",
            "question": "According to the passage, what does the constraint of film photography cultivate?",
            "choices": [
                "A retro aesthetic", "A sense of discipline", "Cheaper costs", "Faster results",
            ], "correct_index": 1,
        }, {
            "level": "C1", "section": "reading",
            "text": "It is a curious paradox that the more connected we become through technology, the "
                     "more some researchers report a sense of isolation, suggesting that the quantity "
                     "of interaction is a poor substitute for its depth.",
            "question": "What paradox does the passage describe?",
            "choices": [
                "More connection but more isolation", "Less technology but more connection",
                "More isolation but less technology", "Less depth but more quantity of friends",
            ], "correct_index": 0,
        }, {
            "level": "C1", "section": "reading",
            "text": "Rather than viewing failure as the opposite of success, some organizational "
                     "theorists now argue it should be treated as an unavoidable byproduct of any "
                     "process ambitious enough to be worth pursuing.",
            "question": "How do some theorists now view failure?",
            "choices": [
                "As proof of poor planning", "As an unavoidable part of ambitious work",
                "As something to be eliminated entirely", "As irrelevant to success",
            ], "correct_index": 1,
        }],
        ("C1", "listening"): [{
            "level": "C1", "section": "listening",
            "text": "What's often mistaken for indecision in skilled negotiators is, more accurately, "
                     "a calculated reluctance to commit prematurely — a way of preserving leverage "
                     "until the other side has revealed enough of its own position.",
            "question": "What does the speaker say is often misunderstood as indecision?",
            "choices": [
                "A lack of negotiation experience", "A deliberate strategy to preserve leverage",
                "Fear of the other side", "An unwillingness to negotiate at all",
            ], "correct_index": 1,
        }, {
            "level": "C1", "section": "listening",
            "text": "What strikes me most about highly experienced editors isn't their vocabulary, "
                     "but their restraint — the discipline to leave a sentence alone once it's "
                     "already doing its job.",
            "question": "What does the speaker say distinguishes experienced editors?",
            "choices": [
                "Their vocabulary", "Their restraint", "Their speed", "Their formal training",
            ], "correct_index": 1,
        }, {
            "level": "C1", "section": "listening",
            "text": "It's often assumed that confidence precedes competence, but in my experience, "
                     "it's usually the other way around — confidence tends to be the byproduct of "
                     "repeated, unglamorous practice.",
            "question": "According to the speaker, what usually comes first?",
            "choices": [
                "Confidence, then competence", "Competence through practice, then confidence",
                "Neither, they arrive together", "Talent alone",
            ], "correct_index": 1,
        }, {
            "level": "C1", "section": "listening",
            "text": "The trouble with most productivity advice is that it treats attention as an "
                     "infinite resource to be better organized, rather than a finite one to be "
                     "carefully protected.",
            "question": "What is the problem with most productivity advice, according to the speaker?",
            "choices": [
                "It's too complicated", "It treats attention as infinite rather than finite",
                "It ignores organization", "It focuses only on time management",
            ], "correct_index": 1,
        }],
    },
    "de": {
        ("A1", "reading"): [{
            "level": "A1", "section": "reading",
            "text": "Ich heiße Anna. Ich bin zehn Jahre alt. Ich habe einen kleinen Hund. Er heißt Max.",
            "question": "Wie heißt Annas Hund?",
            "choices": ["Anna", "Max", "Zehn", "Klein"], "correct_index": 1,
        }, {
            "level": "A1", "section": "reading",
            "text": "Das ist meine Familie. Meine Mutter ist Lehrerin. Mein Vater ist Arzt. Ich habe "
                     "einen Bruder.",
            "question": "Was ist der Beruf der Mutter?",
            "choices": ["Ärztin", "Lehrerin", "Krankenschwester", "Studentin"], "correct_index": 1,
        }, {
            "level": "A1", "section": "reading",
            "text": "Heute ist Montag. Ich gehe jeden Tag zur Schule. Meine Schule ist in der Nähe "
                     "meines Hauses.",
            "question": "Wo ist die Schule?",
            "choices": ["Weit weg", "In der Nähe des Hauses", "In einer anderen Stadt", "Neben dem Markt"],
            "correct_index": 1,
        }, {
            "level": "A1", "section": "reading",
            "text": "Ich habe eine Katze. Sie heißt Lily. Sie ist schwarz und weiß. Sie schläft gern.",
            "question": "Welche Farbe hat Lily?",
            "choices": ["Schwarz und weiß", "Braun", "Orange", "Grau"], "correct_index": 0,
        }],
        ("A1", "listening"): [{
            "level": "A1", "section": "listening",
            "text": "Das ist ein roter Apfel. Er liegt auf dem Tisch. Ich mag Äpfel.",
            "question": "Welche Farbe hat der Apfel?",
            "choices": ["Grün", "Gelb", "Rot", "Blau"], "correct_index": 2,
        }, {
            "level": "A1", "section": "listening",
            "text": "Hallo! Ich heiße Sam. Ich komme aus Kanada. Ich spreche Englisch und Französisch.",
            "question": "Woher kommt Sam?",
            "choices": ["Frankreich", "Kanada", "Deutschland", "Spanien"], "correct_index": 1,
        }, {
            "level": "A1", "section": "listening",
            "text": "Es ist neun Uhr. Die Kinder frühstücken. Sie essen Brot und trinken Milch.",
            "question": "Was essen die Kinder?",
            "choices": ["Brot und Milch", "Reis", "Suppe", "Obst"], "correct_index": 0,
        }, {
            "level": "A1", "section": "listening",
            "text": "Das ist mein Zimmer. Es gibt ein Bett und einen Tisch. Meine Bücher liegen auf "
                     "dem Tisch.",
            "question": "Wo liegen die Bücher?",
            "choices": ["Auf dem Bett", "Auf dem Tisch", "Auf dem Boden", "In der Tasche"], "correct_index": 1,
        }],
        ("A2", "reading"): [{
            "level": "A2", "section": "reading",
            "text": "Jeden Samstag geht Tom mit seiner Mutter auf den Markt. Sie kaufen Obst, "
                     "Gemüse und manchmal frisches Brot. Tom sucht die Äpfel gerne selbst aus.",
            "question": "Wann geht Tom auf den Markt?",
            "choices": ["Jeden Tag", "Jeden Samstag", "Jeden Sonntag", "Nie"], "correct_index": 1,
        }, {
            "level": "A2", "section": "reading",
            "text": "Maria arbeitet in einem kleinen Geschäft im Stadtzentrum. Sie öffnet den Laden "
                     "um acht und schließt ihn um sechs. Sonntags ist der Laden geschlossen.",
            "question": "Wann ist der Laden geschlossen?",
            "choices": ["Jeden Abend", "Sonntags", "Samstags", "Nie"], "correct_index": 1,
        }, {
            "level": "A2", "section": "reading",
            "text": "Letztes Wochenende sind Ali und seine Freunde in der Nähe des Sees zelten "
                     "gegangen. Sie sind geschwommen, haben draußen gekocht und abends Geschichten "
                     "erzählt.",
            "question": "Wo waren Ali und seine Freunde zelten?",
            "choices": ["In den Bergen", "In der Nähe des Sees", "Am Strand", "Im Wald"], "correct_index": 1,
        }, {
            "level": "A2", "section": "reading",
            "text": "Meine Schwester lernt gerade kochen. Gestern hat sie eine Hühnersuppe gemacht, "
                     "aber sie hat vergessen, Salz hinzuzufügen, deshalb schmeckte sie etwas seltsam.",
            "question": "Was war falsch an der Suppe?",
            "choices": ["Sie war zu salzig", "Es fehlte Salz", "Sie war zu scharf", "Sie war kalt"],
            "correct_index": 1,
        }],
        ("A2", "listening"): [{
            "level": "A2", "section": "listening",
            "text": "Gestern hat es den ganzen Tag geregnet, deshalb sind wir zu Hause geblieben "
                     "und haben einen Film gesehen. Heute scheint die Sonne, deshalb gehen wir "
                     "im Park spazieren.",
            "question": "Was machen sie heute?",
            "choices": ["Einen Film sehen", "Zu Hause bleiben", "Im Park spazieren gehen", "Auf Regen warten"],
            "correct_index": 2,
        }, {
            "level": "A2", "section": "listening",
            "text": "Wir planen unseren Sommerurlaub. Meine Eltern wollen in die Berge fahren, aber "
                     "ich würde lieber an den Strand gehen und jeden Tag schwimmen.",
            "question": "Was möchte die sprechende Person machen?",
            "choices": ["In die Berge fahren", "An den Strand gehen", "Zu Hause bleiben", "Eine Stadt besuchen"],
            "correct_index": 1,
        }, {
            "level": "A2", "section": "listening",
            "text": "Der Bus hatte heute Morgen Verspätung, deshalb habe ich meinen ersten Unterricht "
                     "verpasst. Meine Lehrerin war nicht glücklich, aber sie hat mich trotzdem "
                     "reingelassen.",
            "question": "Warum hat die Person den Unterricht verpasst?",
            "choices": ["Sie ist spät aufgewacht", "Der Bus hatte Verspätung", "Sie war krank", "Sie hat die Zeit vergessen"],
            "correct_index": 1,
        }, {
            "level": "A2", "section": "listening",
            "text": "Freitags isst unsere Familie immer zusammen zu Abend und schaut danach einen "
                     "Film. Das ist mein Lieblingstag der Woche.",
            "question": "Was machen sie freitags nach dem Abendessen?",
            "choices": ["Spazieren gehen", "Einen Film schauen", "Spiele spielen", "Früh schlafen gehen"],
            "correct_index": 1,
        }],
        ("B1", "reading"): [{
            "level": "B1", "section": "reading",
            "text": "Obwohl die kleine Bäckerei in der Ulmenstraße keine Webseite hat und nur bis "
                     "mittags geöffnet ist, ist sie zu einem der beliebtesten Orte der Stadt "
                     "geworden — hauptsächlich durch Mundpropaganda von Stammkunden.",
            "question": "Warum ist die Bäckerei so beliebt geworden?",
            "choices": [
                "Sie hat eine sehr gute Webseite", "Sie hat lange geöffnet", "Kunden empfehlen sie weiter",
                "Sie ist gerade in die Ulmenstraße gezogen",
            ], "correct_index": 2,
        }, {
            "level": "B1", "section": "reading",
            "text": "Öffentliche Bibliotheken waren früher ruhige Orte zum Lesen, aber viele haben "
                     "sich in den letzten Jahren verändert und bieten jetzt Workshops, Filmabende "
                     "und sogar Raum für kleine Firmentreffen an.",
            "question": "Wie haben sich Bibliotheken laut dem Text verändert?",
            "choices": [
                "Sie haben geschlossen", "Sie bieten jetzt mehr Aktivitäten an", "Sie sind ruhiger geworden",
                "Sie verleihen keine Bücher mehr",
            ], "correct_index": 1,
        }, {
            "level": "B1", "section": "reading",
            "text": "Als Elena für die Arbeit in eine neue Stadt zog, kannte sie niemanden. Sie "
                     "beschloss, einem lokalen Sportverein beizutreten, was sich als der schnellste "
                     "Weg herausstellte, Freunde zu finden.",
            "question": "Wie hat Elena in der neuen Stadt Freunde gefunden?",
            "choices": [
                "Durch ihre Arbeit", "Durch einen Sportverein", "Durch Nachbarn", "Indem sie zu Hause blieb",
            ], "correct_index": 1,
        }, {
            "level": "B1", "section": "reading",
            "text": "Obwohl der Wetterbericht starken Regen vorhersagte, fand das Open-Air-Konzert "
                     "wie geplant statt, und zum Glück blieb der Regen bis zum allerletzten Lied aus.",
            "question": "Was passierte während des Konzerts?",
            "choices": [
                "Es wurde wegen Regen abgesagt", "Es regnete die ganze Zeit", "Der Regen kam erst am Ende",
                "Es wurde nach drinnen verlegt",
            ], "correct_index": 2,
        }],
        ("B1", "listening"): [{
            "level": "B1", "section": "listening",
            "text": "Früher hatte ich Angst davor, vor anderen zu sprechen, aber seit ich vor zwei "
                     "Jahren einem Debattierclub beigetreten bin, bin ich vor Publikum viel "
                     "selbstbewusster geworden.",
            "question": "Wie hat die Person ihre Angst überwunden?",
            "choices": [
                "Indem sie öffentliches Sprechen vermieden hat", "Indem sie einem Debattierclub beigetreten ist",
                "Indem sie Bücher darüber gelesen hat", "Indem sie nur mit Freunden gesprochen hat",
            ], "correct_index": 1,
        }, {
            "level": "B1", "section": "listening",
            "text": "Ich fand Kochen immer langweilig, bis ich während der Pandemie angefangen habe, "
                     "Kochsendungen zu schauen. Jetzt probiere ich fast jedes Wochenende ein neues "
                     "Rezept aus.",
            "question": "Was hat die Meinung der Person zum Kochen verändert?",
            "choices": [
                "Ein Kochkurs", "Kochsendungen im Fernsehen", "Der Rat einer Freundin", "Ein Kochbuch",
            ], "correct_index": 1,
        }, {
            "level": "B1", "section": "listening",
            "text": "Unser Team hat die Frist verpasst, weil der Kunde die Anforderungen mitten im "
                     "Projekt ständig geändert hat, was uns gezwungen hat, viel Arbeit zu wiederholen.",
            "question": "Warum hat das Team die Frist verpasst?",
            "choices": [
                "Sie haben zu spät angefangen", "Der Kunde änderte ständig die Anforderungen",
                "Das Team war zu klein", "Das Budget war aufgebraucht",
            ], "correct_index": 1,
        }, {
            "level": "B1", "section": "listening",
            "text": "Früher bin ich mit dem Auto zur Arbeit gefahren, aber der Verkehr wurde so "
                     "schlimm, dass ich aufs Fahrrad umgestiegen bin, und jetzt komme ich sogar "
                     "schneller an.",
            "question": "Warum ist die Person aufs Fahrrad umgestiegen?",
            "choices": [
                "Es war billiger", "Der Verkehr war schlecht", "Ihr Auto ist kaputtgegangen",
                "Nur wegen der Fitness",
            ], "correct_index": 1,
        }],
        ("B2", "reading"): [{
            "level": "B2", "section": "reading",
            "text": "Kritiker behaupten seit Langem, dass Homeoffice den Zusammenhalt im Team "
                     "schwächt, doch immer mehr Forschung deutet darauf hin, dass das Gegenteil "
                     "der Fall sein kann, wenn Unternehmen gezielt in strukturierte, "
                     "wiederkehrende Kommunikation investieren.",
            "question": "Was entscheidet laut dem Text, ob Homeoffice dem Teamzusammenhalt schadet?",
            "choices": [
                "Ob Angestellte lieber von zu Hause arbeiten", "Ob die Kommunikation gezielt strukturiert ist",
                "Wie lange es das Unternehmen schon gibt", "Ob Kritiker der Forschung zustimmen",
            ], "correct_index": 1,
        }, {
            "level": "B2", "section": "reading",
            "text": "Trotz der weitverbreiteten Annahme, dass das Leseverhalten zurückgeht, deuten "
                     "aktuelle Umfragen darauf hin, dass jüngere Leser einfach zu digitalen Formaten "
                     "und Hörbüchern wechseln, anstatt das Lesen ganz aufzugeben.",
            "question": "Was deuten die Umfragen über jüngere Leser an?",
            "choices": [
                "Sie lesen weniger als früher", "Sie wechseln zu digitalen Formaten",
                "Sie hören nur noch Podcasts", "Sie bevorzugen gedruckte Bücher",
            ], "correct_index": 1,
        }, {
            "level": "B2", "section": "reading",
            "text": "Die Entscheidung des Stadtrats, den zentralen Platz umzugestalten, stieß bei "
                     "lokalen Ladenbesitzern auf Kritik, die befürchteten, weniger Parkplätze "
                     "würden Kunden vertreiben, obwohl ähnliche Umgestaltungen anderswo den "
                     "Fußgängerverkehr deutlich erhöht hatten.",
            "question": "Warum waren die Ladenbesitzer besorgt?",
            "choices": [
                "Ihnen gefiel das neue Design nicht", "Sie befürchteten Kundenverlust wegen weniger Parkplätzen",
                "Sie wollten mehr Fußgängerverkehr", "Sie waren generell gegen den Stadtrat",
            ], "correct_index": 1,
        }, {
            "level": "B2", "section": "reading",
            "text": "Es ist verlockend, den Erfolg eines Unternehmens einer einzigen visionären "
                     "Gründerfigur zuzuschreiben, aber die historische Analyse zeigt meist eine "
                     "viel unordentlichere Geschichte aus Timing, Glück und den Beiträgen "
                     "übersehener Kollegen.",
            "question": "Was zeigt die historische Analyse meist über Unternehmenserfolg?",
            "choices": [
                "Das Genie eines einzelnen Gründers", "Eine Mischung aus Timing, Glück und Teamarbeit",
                "Reines Glück", "Sorgfältige langfristige Planung",
            ], "correct_index": 1,
        }],
        ("B2", "listening"): [{
            "level": "B2", "section": "listening",
            "text": "Der Ausschuss hat seine Entscheidung vertagt — nicht weil der Vorschlag "
                     "schlecht war, sondern weil zwei Mitglieder fanden, die Budgetprognosen "
                     "seien nicht gegen eine langsamere wirtschaftliche Erholung getestet worden.",
            "question": "Warum hat der Ausschuss die Entscheidung vertagt?",
            "choices": [
                "Der Vorschlag hatte keine Substanz", "Das Budget sollte gegen eine langsamere Erholung getestet werden",
                "Zwei Mitglieder sind zurückgetreten", "Das Budget war schon genehmigt",
            ], "correct_index": 1,
        }, {
            "level": "B2", "section": "listening",
            "text": "Es ist ein weitverbreiteter Irrtum, dass Multitasking uns produktiver macht; "
                     "tatsächlich zeigen die meisten Studien, dass ständiges Wechseln zwischen "
                     "Aufgaben uns verlangsamt und Fehler erhöht.",
            "question": "Was zeigen die meisten Studien über Multitasking?",
            "choices": [
                "Es steigert die Produktivität", "Es verlangsamt uns und erhöht Fehler", "Es hat keine Wirkung",
                "Es funktioniert nur bei einfachen Aufgaben",
            ], "correct_index": 1,
        }, {
            "level": "B2", "section": "listening",
            "text": "Das Unternehmen hat den Produktstart verschoben, nicht wegen technischer "
                     "Probleme, sondern weil frühes Kundenfeedback nahelegte, dass das Preismodell "
                     "komplett überdacht werden sollte.",
            "question": "Warum wurde der Start verschoben?",
            "choices": [
                "Technische Probleme", "Bedenken beim Preismodell", "Kundenmangel", "Produktionsverzögerungen",
            ], "correct_index": 1,
        }, {
            "level": "B2", "section": "listening",
            "text": "Viele nehmen an, dass längere Arbeitszeiten automatisch zu besseren Ergebnissen "
                     "führen, aber die sprechende Person argumentiert, dass Erholung genauso "
                     "entscheidend für dauerhafte Leistung ist.",
            "question": "Was ist laut der sprechenden Person genauso wichtig wie Arbeitsstunden?",
            "choices": [
                "Erholung", "Gehaltserhöhungen", "Teamgröße", "Der Standort des Büros",
            ], "correct_index": 0,
        }],
        ("C1", "reading"): [{
            "level": "C1", "section": "reading",
            "text": "Es wäre zu kurz gegriffen, die plötzliche Rückkehr des Interesses an "
                     "Schallplatten allein mit Nostalgie zu erklären; für viele jüngere Sammler "
                     "liegt der Reiz vielmehr in der bewussten Umständlichkeit des Formats — dem "
                     "Ritual des Anfassens, der auferlegten Geduld — in einem sonst reibungslosen "
                     "digitalen Zeitalter.",
            "question": "Was ist laut dem Autor der Hauptreiz von Schallplatten für jüngere Sammler?",
            "choices": [
                "Nostalgie für die Vergangenheit", "Das bewusste, entschleunigte Ritual des Formats",
                "Niedrigerer Preis als digitale Musik", "Bessere Klangqualität als Streaming",
            ], "correct_index": 1,
        }, {
            "level": "C1", "section": "reading",
            "text": "Das wiedererwachte Interesse an analoger Fotografie lässt sich nicht einfach "
                     "als Retro-Trend abtun; für viele Praktizierende fördern die bewussten "
                     "Einschränkungen des Films — begrenzte Aufnahmen, keine sofortige Vorschau — "
                     "eine Disziplin, die digitale Fülle eher untergräbt.",
            "question": "Was fördern laut dem Text die Einschränkungen der Filmfotografie?",
            "choices": [
                "Eine Retro-Ästhetik", "Ein Gefühl von Disziplin", "Geringere Kosten", "Schnellere Ergebnisse",
            ], "correct_index": 1,
        }, {
            "level": "C1", "section": "reading",
            "text": "Es ist ein merkwürdiges Paradox, dass wir uns umso isolierter fühlen, je "
                     "vernetzter wir durch Technologie werden — was darauf hindeutet, dass die "
                     "Menge an Interaktion ein schlechter Ersatz für ihre Tiefe ist.",
            "question": "Welches Paradox beschreibt der Text?",
            "choices": [
                "Mehr Verbindung, aber mehr Isolation", "Weniger Technologie, aber mehr Verbindung",
                "Mehr Isolation, aber weniger Technologie", "Weniger Tiefe, aber mehr Freunde",
            ], "correct_index": 0,
        }, {
            "level": "C1", "section": "reading",
            "text": "Anstatt Scheitern als das Gegenteil von Erfolg zu betrachten, argumentieren "
                     "manche Organisationstheoretiker inzwischen, dass es als unvermeidliches "
                     "Nebenprodukt jedes Prozesses gesehen werden sollte, der ambitioniert genug "
                     "ist, um verfolgt zu werden.",
            "question": "Wie betrachten manche Theoretiker Scheitern inzwischen?",
            "choices": [
                "Als Beweis für schlechte Planung", "Als unvermeidlichen Teil ambitionierter Arbeit",
                "Als etwas, das komplett vermieden werden sollte", "Als irrelevant für den Erfolg",
            ], "correct_index": 1,
        }],
        ("C1", "listening"): [{
            "level": "C1", "section": "listening",
            "text": "Was bei erfahrenen Verhandlungsführern oft als Unentschlossenheit "
                     "missverstanden wird, ist in Wirklichkeit eine kalkulierte Zurückhaltung, "
                     "sich nicht vorschnell festzulegen — um Verhandlungsspielraum zu bewahren, "
                     "bis die Gegenseite genug von der eigenen Position preisgegeben hat.",
            "question": "Was wird laut dem Sprecher oft als Unentschlossenheit missverstanden?",
            "choices": [
                "Mangelnde Verhandlungserfahrung", "Eine bewusste Strategie zur Wahrung von Verhandlungsspielraum",
                "Angst vor der Gegenseite", "Die Unwilligkeit überhaupt zu verhandeln",
            ], "correct_index": 1,
        }, {
            "level": "C1", "section": "listening",
            "text": "Was mich an sehr erfahrenen Lektoren am meisten beeindruckt, ist nicht ihr "
                     "Wortschatz, sondern ihre Zurückhaltung — die Disziplin, einen Satz in Ruhe zu "
                     "lassen, sobald er seine Aufgabe bereits erfüllt.",
            "question": "Was zeichnet laut dem Sprecher erfahrene Lektoren aus?",
            "choices": [
                "Ihren Wortschatz", "Ihre Zurückhaltung", "Ihre Geschwindigkeit", "Ihre formale Ausbildung",
            ], "correct_index": 1,
        }, {
            "level": "C1", "section": "listening",
            "text": "Man nimmt oft an, dass Selbstvertrauen der Kompetenz vorausgeht, aber meiner "
                     "Erfahrung nach ist es meist umgekehrt — Selbstvertrauen ist meist das "
                     "Nebenprodukt wiederholter, unglamouröser Übung.",
            "question": "Was kommt laut dem Sprecher normalerweise zuerst?",
            "choices": [
                "Selbstvertrauen, dann Kompetenz", "Kompetenz durch Übung, dann Selbstvertrauen",
                "Keins von beidem, sie entstehen gleichzeitig", "Nur Talent",
            ], "correct_index": 1,
        }, {
            "level": "C1", "section": "listening",
            "text": "Das Problem mit den meisten Produktivitätsratschlägen ist, dass sie "
                     "Aufmerksamkeit als unendliche Ressource behandeln, die man nur besser "
                     "organisieren muss, statt als endliche Ressource, die sorgfältig geschützt "
                     "werden muss.",
            "question": "Was ist laut dem Sprecher das Problem mit den meisten Produktivitätsratschlägen?",
            "choices": [
                "Sie sind zu kompliziert", "Sie behandeln Aufmerksamkeit als unendlich statt endlich",
                "Sie ignorieren Organisation", "Sie konzentrieren sich nur auf Zeitmanagement",
            ], "correct_index": 1,
        }],
    },
}
