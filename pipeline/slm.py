"""Option 3 : extraction de transactions depuis du texte libre avec un SLM (Ollama).

Flux : Texte -> SLM (réponse JSON imposée) -> Validation / Transformation (Python)
       -> même format qu'une ligne de CSV -> même traitement que les CSV.

Le modèle ne fait que ce que le code ne sait pas faire (comprendre la phrase).
Tout ce qui peut être déterministe est fait en Python (pays, année, vérifications).
"""
import json
import os
import re
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation

from pipeline.loader import parse_row

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
SLM_MODEL = os.getenv("SLM_MODEL", "qwen2.5:1.5b")
DEFAULT_YEAR = int(os.getenv("SLM_DEFAULT_YEAR", "2026"))   # si le texte ne donne pas l'année
TIMEOUT = 180   # secondes (le 1er appel charge le modèle en mémoire)

COUNTRY_BY_IBAN_CODE = {
    "FR": "France", "DE": "Allemagne", "ES": "Espagne", "IT": "Italie",
    "BE": "Belgique", "NL": "Pays-Bas", "PT": "Portugal", "LU": "Luxembourg",
    "CH": "Suisse", "GB": "Royaume-Uni", "AT": "Autriche", "IE": "Irlande",
}
IBAN_FORMAT = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{4,30}$")

# Format de réponse IMPOSÉ au modèle (Ollama "structured outputs")
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "jour": {"type": "integer"},
        "mois": {"type": "integer"},
        "annee": {"type": "integer"},
        "heure": {"type": "integer"},
        "minute": {"type": "integer"},
        "iban_origine": {"type": "string"},
        "banque_source": {"type": "string"},
        "iban_destinataire": {"type": "string"},
        "montant": {"type": "number"},
    },
    "required": ["jour", "mois", "annee", "heure", "minute", "iban_origine",
                 "banque_source", "iban_destinataire", "montant"],
}

SYSTEM_PROMPT = """Tu extrais UNE transaction bancaire d'un texte en francais.
Reponds uniquement avec un objet JSON contenant :
- jour, mois (1 a 12), annee (0 si absente), heure, minute : la date et l'heure du virement
- iban_origine : le compte qui ENVOIE l'argent, recopie exactement
- banque_source : la banque qui envoie, "" si elle n'est pas nommee
- iban_destinataire : le compte qui RECOIT l'argent, recopie exactement
- montant : le montant en euros, nombre decimal avec un point (1 250,50 -> 1250.5)
N'invente rien : recopie les valeurs presentes dans le texte."""

EXAMPLE_TEXT = ("Le 5 juin a 8h05, la Banque Postale a vire 1 300,25 euros du compte "
                "FR1420041010050500013M02606 vers le compte NL91ABNA0417164300.")
EXAMPLE_ANSWER = {
    "jour": 5, "mois": 6, "annee": 0, "heure": 8, "minute": 5,
    "iban_origine": "FR1420041010050500013M02606", "banque_source": "Banque Postale",
    "iban_destinataire": "NL91ABNA0417164300", "montant": 1300.25,
}


class SLMExtractionError(ValueError):
    """Le texte ne contient pas une transaction exploitable (ou le modèle s'est trompé)."""


class SLMUnavailableError(Exception):
    """Le service Ollama est injoignable (erreur temporaire -> retry)."""


def ask_slm(text):
    """Étape SLM : envoie le texte au modèle et renvoie sa réponse JSON (dict)."""
    payload = {
        "model": SLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": EXAMPLE_TEXT},
            {"role": "assistant", "content": json.dumps(EXAMPLE_ANSWER)},
            {"role": "user", "content": text},
        ],
        "format": RESPONSE_SCHEMA,                   # réponse JSON imposée
        "stream": False,
        "options": {"temperature": 0, "seed": 42},   # réponses reproductibles
    }
    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise SLMUnavailableError(f"Ollama injoignable ({OLLAMA_URL}) : {e}") from e

    try:
        return json.loads(body["message"]["content"])
    except (KeyError, json.JSONDecodeError) as e:
        raise SLMExtractionError(f"réponse du modèle illisible : {body}") from e


def _numbers_in(text):
    """Tous les nombres présents dans le texte ("1 250,50" -> Decimal('1250.50'))."""
    numbers = set()
    for raw in re.findall(r"\d[\d  ]*(?:[.,]\d+)?", text):
        cleaned = re.sub(r"[\s ]", "", raw).replace(",", ".")
        try:
            numbers.add(Decimal(cleaned))
        except InvalidOperation:
            pass
    return numbers


def to_row(answer, text, source="<texte>"):
    """Étape validation / transformation : réponse du modèle -> ligne au format CSV.

    Fonction pure : ne dépend que de la réponse du modèle et du texte d'origine.
    """
    compact_text = re.sub(r"\s+", "", text).upper()
    try:
        iban_origine = re.sub(r"\s+", "", str(answer["iban_origine"])).upper()
        iban_destinataire = re.sub(r"\s+", "", str(answer["iban_destinataire"])).upper()
        year = int(answer["annee"]) or DEFAULT_YEAR
        dt = (f"{year:04d}-{int(answer['mois']):02d}-{int(answer['jour']):02d} "
              f"{int(answer['heure']):02d}:{int(answer['minute']):02d}:00")
        montant = Decimal(str(answer["montant"])).quantize(Decimal("0.01"))
        banque = str(answer.get("banque_source") or "").strip() or "Inconnue"
    except (KeyError, TypeError, ValueError, InvalidOperation) as e:
        raise SLMExtractionError(f"{source} : réponse incomplète du modèle {answer}") from e

    # Garde-fous anti-hallucination : les valeurs doivent VENIR du texte
    for name, iban in (("iban_origine", iban_origine), ("iban_destinataire", iban_destinataire)):
        if not IBAN_FORMAT.match(iban):
            raise SLMExtractionError(f"{source} : IBAN invalide '{iban}' ({name})")
        if iban not in compact_text:
            raise SLMExtractionError(f"{source} : IBAN '{iban}' absent du texte ({name})")
    if iban_origine == iban_destinataire:
        raise SLMExtractionError(f"{source} : émetteur et destinataire identiques")
    if montant not in _numbers_in(text):
        raise SLMExtractionError(f"{source} : montant {montant} absent du texte")

    # Transformation déterministe : le pays se déduit du code de l'IBAN
    return {
        "datetime_transaction": dt,
        "iban_origine": iban_origine,
        "pays_source": COUNTRY_BY_IBAN_CODE.get(iban_origine[:2], "Inconnu"),
        "banque_source": banque,
        "iban_destinataire": iban_destinataire,
        "pays_destinataire": COUNTRY_BY_IBAN_CODE.get(iban_destinataire[:2], "Inconnu"),
        "montant": str(montant),
    }


def extract_transactions(content, source="<texte>"):
    """Texte (bytes) -> liste de transactions validées (même format que le loader CSV)."""
    text = content.decode("utf-8-sig").strip()
    if not text:
        raise SLMExtractionError(f"{source} : texte vide")
    answer = ask_slm(text)
    row = to_row(answer, text, source)
    return [parse_row(row, 1, source)]   # même validation que les CSV