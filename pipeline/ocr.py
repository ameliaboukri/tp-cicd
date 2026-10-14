"""Option 2 : extraction de transactions depuis des images (OCR avec Tesseract).

Flux : Image -> OCR -> Extraction des informations -> Validation / Transformation
       -> même format qu'une ligne de CSV -> même traitement que les CSV.
"""
import io
import os
import re
import shutil
from pathlib import Path

import pytesseract
from PIL import Image

from pipeline.loader import parse_row

# Emplacement par défaut de Tesseract sous Windows (pas toujours dans le PATH)
WINDOWS_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Une expression régulière par champ : "Libellé : valeur" (espaces tolérés)
FIELD_PATTERNS = {
    "datetime_transaction": r"Date\s*:\s*([^\n]+)",
    "iban_origine": r"IBAN\s+emetteur\s*:\s*([^\n]+)",
    "pays_source": r"Pays\s+emetteur\s*:\s*([^\n]+)",
    "banque_source": r"Banque\s+emettrice\s*:\s*([^\n]+)",
    "iban_destinataire": r"IBAN\s+destinataire\s*:\s*([^\n]+)",
    "pays_destinataire": r"Pays\s+destinataire\s*:\s*([^\n]+)",
    "montant": r"Montant\s*:\s*([^\n]+)",
}
IBAN_FORMAT = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$")


class OCRExtractionError(ValueError):
    """L'image ne contient pas une transaction lisible et valide."""


def _configure_tesseract():
    """Indique à pytesseract où trouver le programme Tesseract."""
    cmd = os.getenv("TESSERACT_CMD")
    if not cmd and shutil.which("tesseract") is None and Path(WINDOWS_TESSERACT).exists():
        cmd = WINDOWS_TESSERACT
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd


def ocr_image(content):
    """Étape OCR : image (bytes) -> texte brut."""
    _configure_tesseract()
    image = Image.open(io.BytesIO(content)).convert("L")  # niveaux de gris
    return pytesseract.image_to_string(image)


def _clean_iban(value):
    return re.sub(r"\s+", "", value).upper()


def _clean_amount(value):
    # "6 200,00 EUR" -> "6200.00"
    value = re.sub(r"(?i)eur|€", "", value)
    return re.sub(r"\s+", "", value).replace(",", ".")


def extract_fields(text, source="<image>"):
    """Étape extraction + transformation : texte OCR -> dict au format d'une ligne CSV.

    Fonction pure : ne dépend que du texte reçu.
    """
    row, missing = {}, []
    for field, pattern in FIELD_PATTERNS.items():
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            row[field] = match.group(1).strip()
        else:
            missing.append(field)
    if missing:
        raise OCRExtractionError(f"{source} : champs introuvables dans l'image {missing}")

    # Transformation : on corrige les petits défauts typiques de l'OCR
    row["datetime_transaction"] = re.sub(r"\s+", " ", row["datetime_transaction"])
    row["iban_origine"] = _clean_iban(row["iban_origine"])
    row["iban_destinataire"] = _clean_iban(row["iban_destinataire"])
    row["montant"] = _clean_amount(row["montant"])

    for field in ("iban_origine", "iban_destinataire"):
        if not IBAN_FORMAT.match(row[field]):
            raise OCRExtractionError(f"{source} : IBAN illisible '{row[field]}' ({field})")
    return row


def extract_transactions(content, source="<image>"):
    """Image (bytes) -> liste de transactions validées (même format que le loader CSV)."""
    text = ocr_image(content)
    row = extract_fields(text, source)
    return [parse_row(row, 1, source)]   # même validation que les CSV