"""Chargement et validation des fichiers CSV de transactions."""
import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

REQUIRED_COLUMNS = [
    "datetime_transaction",
    "iban_origine",
    "pays_source",
    "banque_source",
    "iban_destinataire",
    "pays_destinataire",
    "montant",
]
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
TEXT_COLUMNS = ["iban_origine", "pays_source", "banque_source",
                "iban_destinataire", "pays_destinataire"]


class InvalidCSVError(ValueError):
    """Le fichier CSV ne respecte pas le format attendu."""


def parse_row(row, line, source):
    """Valide une ligne et la convertit dans les bons types."""
    raw_dt = row.get("datetime_transaction") or ""
    try:
        dt = datetime.strptime(raw_dt, DATETIME_FORMAT)
    except ValueError:
        raise InvalidCSVError(f"{source} ligne {line} : date invalide '{raw_dt}'")

    raw_amount = row.get("montant") or ""
    try:
        montant = Decimal(raw_amount)
    except InvalidOperation:
        raise InvalidCSVError(f"{source} ligne {line} : montant invalide '{raw_amount}'")
    if not montant.is_finite() or montant <= 0:
        raise InvalidCSVError(f"{source} ligne {line} : montant doit être > 0 ('{raw_amount}')")

    for col in TEXT_COLUMNS:
        if not (row.get(col) or "").strip():
            raise InvalidCSVError(f"{source} ligne {line} : colonne '{col}' vide")

    return {
        "datetime_transaction": dt,
        "iban_origine": row["iban_origine"].strip(),
        "pays_source": row["pays_source"].strip(),
        "banque_source": row["banque_source"].strip(),
        "iban_destinataire": row["iban_destinataire"].strip(),
        "pays_destinataire": row["pays_destinataire"].strip(),
        "montant": montant,
    }


def parse_csv_text(text, source="<texte>"):
    """Analyse le contenu texte d'un CSV (réutilisable pour le S3 au niveau 2)."""
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise InvalidCSVError(f"{source} : fichier vide")

    missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
    if missing:
        raise InvalidCSVError(f"{source} : colonnes manquantes {missing}")

    # ligne 1 = en-tête, donc les données commencent ligne 2
    transactions = [parse_row(row, i, source) for i, row in enumerate(reader, start=2)]
    if not transactions:
        raise InvalidCSVError(f"{source} : aucune transaction")
    return transactions


def load_csv_file(path):
    """Lit un fichier CSV local et renvoie la liste des transactions validées."""
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")  # -sig : gère le BOM d'Excel
    return parse_csv_text(text, source=path.name)