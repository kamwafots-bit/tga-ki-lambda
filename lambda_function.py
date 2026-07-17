import os
import json
import re
import urllib.request
import urllib.error
from typing import Dict, Any, List, Tuple

import boto3


# ============================================================
# EINSTELLUNGEN AUS LAMBDA ENVIRONMENT VARIABLES
# ============================================================

S3_BUCKET_NAME = os.environ.get("S3_BUCKET", "wagpteam1")
DB_KEY = os.environ.get("DB_KEY", "db.json")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

TOP_N = 8
MAX_CHARS_PER_TREFFER = 2500
MAX_SEARCH_TERMS = 35

s3 = boto3.client("s3")


# ============================================================
# HTTP RESPONSE
# WICHTIG:
# KEINE Access-Control-Allow-Origin Header hier setzen!
# CORS wird über Lambda Function URL eingestellt.
# ============================================================

def response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json"
        },
        "body": json.dumps(body, ensure_ascii=False)
    }


# ============================================================
# REQUEST BODY LESEN
# ============================================================

def get_payload(event: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(event, dict):
        return {}

    body = event.get("body", event)

    if isinstance(body, str):
        try:
            return json.loads(body)
        except Exception:
            return {}

    if isinstance(body, dict):
        return body

    return {}


# ============================================================
# DB.JSON AUS S3 LADEN
# ============================================================

def lade_db_aus_s3() -> Dict[str, Any]:
    obj = s3.get_object(
        Bucket=S3_BUCKET_NAME,
        Key=DB_KEY
    )

    text = obj["Body"].read().decode("utf-8")
    return json.loads(text)


# ============================================================
# TEXT NORMALISIEREN
# ============================================================

def text_sauber_machen(text: str) -> str:
    text = str(text).lower()
    text = text.replace("ä", "ae")
    text = text.replace("ö", "oe")
    text = text.replace("ü", "ue")
    text = text.replace("ß", "ss")
    text = re.sub(r"[^a-zA-Z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def frage_zu_keywords(frage: str) -> List[str]:
    stopwords = {
        "was", "ist", "sind", "der", "die", "das", "ein", "eine", "einer",
        "eines", "und", "oder", "in", "im", "am", "an", "auf", "zu", "mit",
        "von", "für", "fuer", "wie", "wo", "welche", "welcher", "welches",
        "warum", "wird", "werden", "kann", "können", "koennen", "ich", "wir",
        "du", "es", "den", "dem", "des", "bei", "nach", "aus", "als", "auch",
        "bitte", "mir", "uns", "über", "ueber", "unter", "nicht", "noch",
        "soll", "sollen", "erkläre", "erklaere", "bedeutet", "bedeuten",
        "gibt", "informationen", "information", "info"
    }

    frage_norm = text_sauber_machen(frage)
    woerter = frage_norm.split()

    keywords = []

    for wort in woerter:
        if len(wort) > 2 and wort not in stopwords:
            keywords.append(wort)

    return keywords


# ============================================================
# TGA-FACHBEGRIFFE UND SYNONYME
# ============================================================

TECHNISCHE_SYNONYME = {
    "datenpunkt": [
        "Datenpunkt",
        "Datenpunkte",
        "Datenpunktliste",
        "GA-Funktionsliste",
        "Funktionsliste",
        "Benutzeradresse",
        "Datenpunktadresse",
        "E/A-Datenpunkt",
        "Eingang",
        "Ausgang",
        "Meldepunkt",
        "Messwert",
        "Sollwert",
        "Istwert"
    ],
    "gebaeudeautomation": [
        "Gebäudeautomation",
        "Gebaeudeautomation",
        "GA",
        "Gebäudeleittechnik",
        "Gebaeudeleittechnik",
        "Automationsebene",
        "Managementebene",
        "Feldebene",
        "DDC",
        "BACnet",
        "Modbus",
        "KNX",
        "M-Bus"
    ],
    "tga": [
        "TGA",
        "Technische Gebäudeausrüstung",
        "Technische Gebaeudeausruestung",
        "Gewerk",
        "Gewerke",
        "Heizung",
        "Lüftung",
        "Lueftung",
        "Sanitär",
        "Sanitaer",
        "Elektrotechnik",
        "MSR"
    ],
    "gewerk": [
        "Gewerk",
        "Gewerke",
        "Fachgewerk",
        "Fachgewerke",
        "Heizung",
        "Lüftung",
        "Sanitär",
        "Elektro",
        "MSR"
    ],
    "lueftung": [
        "Lüftung",
        "Lueftung",
        "Lüftungsanlage",
        "Lueftungsanlage",
        "Lüftungstechnik",
        "Lueftungstechnik",
        "RLT",
        "Raumlufttechnik",
        "Volumenstrom",
        "Klappe",
        "Ventilator"
    ],
    "heizung": [
        "Heizung",
        "Heizkreis",
        "Wärmeerzeuger",
        "Waermeerzeuger",
        "Ventil",
        "Pumpe",
        "Vorlauf",
        "Rücklauf",
        "Ruecklauf",
        "Regelung",
        "Sollwert",
        "Istwert"
    ],
    "kuehlung": [
        "Kühlung",
        "Kuehlung",
        "Kälte",
        "Kaelte",
        "Kältemaschine",
        "Kaeltemaschine",
        "Kühlwasser",
        "Kuehlwasser",
        "Kälteanlage",
        "Kaelteanlage"
    ],
    "regelung": [
        "Regelung",
        "Regelstrategie",
        "Regler",
        "Sollwert",
        "Istwert",
        "Führungsgröße",
        "Fuehrungsgroesse",
        "Stellgröße",
        "Stellgroesse",
        "Betriebsart",
        "Zeitprogramm"
    ],
    "sensor": [
        "Sensor",
        "Fühler",
        "Fuehler",
        "Temperatur",
        "Feuchte",
        "Druck",
        "Differenzdruck",
        "Volumenstrom",
        "Messwert"
    ],
    "aktor": [
        "Aktor",
        "Stellantrieb",
        "Ventil",
        "Klappe",
        "Pumpe",
        "Schaltbefehl",
        "Ausgang"
    ]
}


def alle_bekannten_fachbegriffe() -> List[str]:
    begriffe = []

    for key, values in TECHNISCHE_SYNONYME.items():
        begriffe.append(key)
        begriffe.extend(values)

    seen = set()
    result = []

    for begriff in begriffe:
        norm = text_sauber_machen(begriff)

        if norm and norm not in seen:
            seen.add(norm)
            result.append(begriff)

    return result


BEKANNTE_FACHBEGRIFFE = alle_bekannten_fachbegriffe()


# ============================================================
# FUZZY MATCHING
# ============================================================

def levenshtein_limited(a: str, b: str, max_dist: int) -> int:
    if abs(len(a) - len(b)) > max_dist:
        return max_dist + 1

    previous = list(range(len(b) + 1))

    for i, ca in enumerate(a, start=1):
        current = [i]
        min_current = i

        for j, cb in enumerate(b, start=1):
            insert_cost = current[j - 1] + 1
            delete_cost = previous[j] + 1
            replace_cost = previous[j - 1] + (0 if ca == cb else 1)

            value = min(insert_cost, delete_cost, replace_cost)
            current.append(value)

            if value < min_current:
                min_current = value

        if min_current > max_dist:
            return max_dist + 1

        previous = current

    return previous[-1]


def erlaubte_distanz(wort: str) -> int:
    laenge = len(wort)

    if laenge <= 5:
        return 1

    if laenge <= 11:
        return 2

    return 3


def finde_aehnlichen_fachbegriff(wort: str) -> str:
    wort_norm = text_sauber_machen(wort).replace(" ", "")

    if len(wort_norm) < 4:
        return ""

    bester_begriff = ""
    beste_distanz = 999
    max_dist = erlaubte_distanz(wort_norm)

    for begriff in BEKANNTE_FACHBEGRIFFE:
        begriff_norm = text_sauber_machen(begriff).replace(" ", "")

        if not begriff_norm:
            continue

        if abs(len(wort_norm) - len(begriff_norm)) > max_dist:
            continue

        distanz = levenshtein_limited(wort_norm, begriff_norm, max_dist)

        if distanz < beste_distanz and distanz <= max_dist:
            beste_distanz = distanz
            bester_begriff = begriff

    return bester_begriff


def synonyme_fuer_term(term: str) -> List[str]:
    term_norm = text_sauber_machen(term)
    result = []

    for key, werte in TECHNISCHE_SYNONYME.items():
        alle = [key] + werte
        alle_norm = [text_sauber_machen(x) for x in alle]

        if term_norm in alle_norm:
            result.extend(werte)

    return result


def dedupe_terms(terms: List[str]) -> List[str]:
    seen = set()
    result = []

    for term in terms:
        if not term:
            continue

        term = str(term).strip()
        norm = text_sauber_machen(term)

        if len(norm) < 2:
            continue

        if norm not in seen:
            seen.add(norm)
            result.append(term)

    return result


# ============================================================
# FRAGE KORRIGIEREN UND SUCHBEGRIFFE ERZEUGEN
# ============================================================

def korrigiere_frage_lokal(frage: str) -> str:
    def ersetze_wort(match):
        wort = match.group(0)
        fachbegriff = finde_aehnlichen_fachbegriff(wort)

        if fachbegriff:
            return fachbegriff

        return wort

    return re.sub(r"[A-Za-zÄÖÜäöüß0-9-]{4,}", ersetze_wort, frage)


def erstelle_query_plan(frage: str) -> Dict[str, Any]:
    korrigierte_frage = korrigiere_frage_lokal(frage)

    terms = []

    terms.extend(frage_zu_keywords(frage))
    terms.extend(frage_zu_keywords(korrigierte_frage))

    for keyword in list(terms):
        fachbegriff = finde_aehnlichen_fachbegriff(keyword)

        if fachbegriff:
            terms.append(fachbegriff)
            terms.extend(synonyme_fuer_term(fachbegriff))

        terms.extend(synonyme_fuer_term(keyword))

    terms = dedupe_terms(terms)

    return {
        "original_question": frage,
        "corrected_question": korrigierte_frage,
        "search_terms": terms[:MAX_SEARCH_TERMS]
    }


# ============================================================
# SCORE BERECHNEN
# ============================================================

def count_exact_word(text_norm: str, word_norm: str) -> int:
    return len(re.findall(r"\b" + re.escape(word_norm) + r"\b", text_norm))


def fuzzy_score_keyword(keyword_norm: str, words_set: set) -> int:
    if len(keyword_norm) < 4:
        return 0

    max_dist = erlaubte_distanz(keyword_norm)
    score = 0
    matches = 0

    for wort in words_set:
        if len(wort) < 4:
            continue

        if abs(len(wort) - len(keyword_norm)) > max_dist:
            continue

        if wort == keyword_norm:
            continue

        distanz = levenshtein_limited(keyword_norm, wort, max_dist)

        if distanz <= max_dist:
            score += max(1, max_dist + 1 - distanz)
            matches += 1

        if matches >= 6:
            break

    return score


def berechne_treffer_score(
    text: str,
    filename: str,
    query_plan: Dict[str, Any]
) -> int:
    text_norm = text_sauber_machen(text)
    filename_norm = text_sauber_machen(filename)
    words_set = set(text_norm.split())

    score = 0

    original_norm = text_sauber_machen(query_plan.get("original_question", ""))
    corrected_norm = text_sauber_machen(query_plan.get("corrected_question", ""))

    if corrected_norm and len(corrected_norm) > 4 and corrected_norm in text_norm:
        score += 12

    if original_norm and len(original_norm) > 4 and original_norm in text_norm:
        score += 6

    terms = query_plan.get("search_terms", [])

    for term in terms:
        term_norm = text_sauber_machen(term)

        if len(term_norm) < 3:
            continue

        term_words = term_norm.split()

        if len(term_words) > 1:
            phrase_count = text_norm.count(term_norm)

            if phrase_count > 0:
                score += phrase_count * 14

            wichtige_woerter = [w for w in term_words if len(w) > 2]

            if wichtige_woerter and all(w in words_set for w in wichtige_woerter):
                score += 5

        else:
            exact_count = count_exact_word(text_norm, term_norm)

            if exact_count > 0:
                score += exact_count * 6
            else:
                score += fuzzy_score_keyword(term_norm, words_set)

            substring_hits = 0

            for wort in words_set:
                if term_norm in wort and term_norm != wort:
                    substring_hits += 1

                if substring_hits >= 5:
                    break

            score += substring_hits

        if term_norm in filename_norm:
            score += 2

    return score


# ============================================================
# SUCHE IN DB.JSON
# ============================================================

def suche_in_db(frage: str, top_n: int = TOP_N) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    db = lade_db_aus_s3()

    query_plan = erstelle_query_plan(frage)

    if not query_plan.get("search_terms"):
        return [], query_plan

    treffer = []

    for dokument in db.get("documents", []):
        filename = dokument.get("filename", "unbekannt")

        for page in dokument.get("pages", []):
            page_number = page.get("page", "?")
            text = page.get("text", "")

            if not text or not text.strip():
                continue

            score = berechne_treffer_score(
                text=text,
                filename=filename,
                query_plan=query_plan
            )

            if score > 0:
                treffer.append({
                    "score": score,
                    "filename": filename,
                    "page": page_number,
                    "text": text.strip()
                })

    treffer.sort(key=lambda x: x["score"], reverse=True)
    return treffer[:top_n], query_plan


# ============================================================
# KONTEXT FÜR CLAUDE BAUEN
# ============================================================

def baue_kontext(treffer: List[Dict[str, Any]]) -> str:
    teile = []

    for i, t in enumerate(treffer, start=1):
        text = t["text"].replace("\n", " ")

        if len(text) > MAX_CHARS_PER_TREFFER:
            text = text[:MAX_CHARS_PER_TREFFER] + "..."

        quelle = (
            f"[Quelle {i}]\n"
            f"Datei: {t['filename']}\n"
            f"Seite: {t['page']}\n"
            f"Treffer-Score: {t['score']}\n"
            f"Textstelle:\n{text}\n"
        )

        teile.append(quelle)

    return "\n" + ("-" * 80 + "\n").join(teile)


# ============================================================
# CLAUDE API AUFRUFEN
# ============================================================

def claude_messages(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2200,
    temperature: float = 0.1
) -> str:
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY fehlt in den Lambda Environment Variables.")

    data = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system_prompt,
        "messages": [
            {
                "role": "user",
                "content": user_prompt
            }
        ]
    }

    request = urllib.request.Request(
        url="https://api.anthropic.com/v1/messages",
        data=json.dumps(data).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=35) as r:
            result = json.loads(r.read().decode("utf-8"))

    except urllib.error.HTTPError as e:
        error_text = e.read().decode("utf-8")
        raise Exception(f"Claude API Fehler: {e.code} - {error_text}")

    antwort_teile = []

    for block in result.get("content", []):
        if block.get("type") == "text":
            antwort_teile.append(block.get("text", ""))

    return "\n\n".join(antwort_teile).strip()


def frage_an_claude(
    frage_original: str,
    query_plan: Dict[str, Any],
    treffer: List[Dict[str, Any]]
) -> str:
    kontext = baue_kontext(treffer)

    corrected_question = query_plan.get("corrected_question", frage_original)
    search_terms = query_plan.get("search_terms", [])

    system_prompt = """
Du bist TGA-KI, ein Fachassistent für TGA-Planer, Gebäudeautomation und MSR-Technik.

Du beantwortest Fragen ausschließlich auf Basis der bereitgestellten Textstellen aus den PDF-Unterlagen.

Regeln:
1. Nutze nur die bereitgestellten Textstellen.
2. Erfinde keine Informationen.
3. Wenn die Antwort aus den Textstellen nicht sicher hervorgeht, sage:
   "Dazu finde ich in den hochgeladenen Unterlagen keine sichere Information."
4. Antworte fachlich, klar und professionell.
5. Nutze Markdown mit Überschriften, Listen und Tabellen, wenn es sinnvoll ist.
6. Nenne am Ende die Quellen mit Dateiname und Seite.
7. Wenn mehrere Quellen relevant sind, kombiniere sie sinnvoll.
8. Wenn die Nutzerfrage Tippfehler enthält, orientiere dich an der korrigierten Suchfrage.
"""

    user_prompt = f"""
Originale Nutzerfrage:
{frage_original}

Korrigierte Suchfrage:
{corrected_question}

Verwendete Suchbegriffe:
{", ".join(search_terms[:20])}

Gefundene Textstellen aus der Datenbank:
{kontext}

Bitte beantworte die Frage auf Basis dieser Textstellen.
"""

    return claude_messages(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=2200,
        temperature=0.1
    )


# ============================================================
# LAMBDA HAUPTFUNKTION
# ============================================================

def lambda_handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method")

    if method == "OPTIONS":
        return response(200, {"message": "CORS OK"})

    payload = get_payload(event)
    frage = payload.get("frage", "").strip()

    if not frage:
        return response(400, {
            "error": "Keine Frage erhalten. Bitte sende JSON mit dem Feld 'frage'."
        })

    try:
        treffer, query_plan = suche_in_db(frage)

        if not treffer:
            return response(200, {
                "antwort": "Dazu finde ich in den hochgeladenen Unterlagen keine sichere Information.",
                "quellen": [],
                "rewrite": {
                    "original_question": query_plan.get("original_question", frage),
                    "corrected_question": query_plan.get("corrected_question", frage),
                    "search_terms": query_plan.get("search_terms", [])
                }
            })

        antwort = frage_an_claude(frage, query_plan, treffer)

        quellen = []

        for t in treffer:
            quellen.append({
                "datei": t["filename"],
                "seite": t["page"],
                "score": t["score"]
            })

        return response(200, {
            "antwort": antwort,
            "quellen": quellen,
            "rewrite": {
                "original_question": query_plan.get("original_question", frage),
                "corrected_question": query_plan.get("corrected_question", frage),
                "search_terms": query_plan.get("search_terms", [])
            }
        })

    except Exception as e:
        return response(500, {
            "error": str(e)
        })