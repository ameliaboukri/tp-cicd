"""Tests de l'option 2 : extraction de transactions depuis des images (OCR)."""
import os
import shutil
from datetime import datetime
from decimal import Decimal

import pytest

from generator.generate_csv import ACCOUNTS
from generator.generate_images import generate_images
from pipeline.main import run
from pipeline.ocr import (
    WINDOWS_TESSERACT,
    OCRExtractionError,
    extract_fields,
    extract_transactions,
)

HAS_TESSERACT = bool(shutil.which("tesseract") or os.getenv("TESSERACT_CMD")
                     or os.path.exists(WINDOWS_TESSERACT))
# En CI (REQUIRE_TESSERACT=1), on ne saute jamais : un Tesseract absent doit faire échouer
REQUIRE_TESSERACT = os.getenv("REQUIRE_TESSERACT") == "1"
needs_tesseract = pytest.mark.skipif(not HAS_TESSERACT and not REQUIRE_TESSERACT,
                                     reason="Tesseract non installé")

# Texte tel que Tesseract peut le renvoyer, avec 2 défauts réels observés :
# un espace parasite dans l'IBAN et "Montant:" collé (+ montant au format français)
TEXTE_OCR = """ORDRE DE VIREMENT

Date : 2026-09-12 14:30:00
IBAN emetteur : FR763000600001 1234567890189
Pays emetteur : France
Banque emettrice : BNP Paribas
IBAN destinataire : DE89370400440532013000
Pays destinataire : Allemagne
Montant: 6 200,00 EUR
"""


def count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# ---------- Tests unitaires (sans Tesseract) : extraction + transformation ----------

def test_extraction_et_transformation():
    row = extract_fields(TEXTE_OCR)
    assert row["datetime_transaction"] == "2026-09-12 14:30:00"
    assert row["iban_origine"] == "FR7630006000011234567890189"   # espace supprimé
    assert row["banque_source"] == "BNP Paribas"
    assert row["iban_destinataire"] == "DE89370400440532013000"
    assert row["montant"] == "6200.00"                             # "6 200,00 EUR"


def test_extraction_champ_manquant():
    with pytest.raises(OCRExtractionError, match="montant"):
        extract_fields(TEXTE_OCR.replace("Montant", "Total"))


def test_extraction_iban_illisible():
    with pytest.raises(OCRExtractionError, match="IBAN illisible"):
        extract_fields(TEXTE_OCR.replace("DE89370400440532013000", "D3?!"))


# ---------- Tests avec Tesseract ----------

@needs_tesseract
def test_ocr_image_de_reference(tmp_path):
    """L'image de l'exemple du sujet (6200 EUR, FR -> DE) est relue correctement."""
    path = generate_images(tmp_path, nb_images=0, seed=0)[0]
    [t] = extract_transactions(path.read_bytes(), path.name)
    assert t["datetime_transaction"] == datetime(2026, 9, 12, 14, 30)
    assert t["iban_origine"] == ACCOUNTS[0]["iban"]
    assert t["banque_source"] == "BNP Paribas"
    assert t["iban_destinataire"] == ACCOUNTS[2]["iban"]
    assert t["montant"] == Decimal("6200.00")


@needs_tesseract
def test_images_dans_la_pipeline(conn, tmp_path):
    """Image -> S3 -> OCR -> traitement -> base, avec les bons flags."""
    generate_images(tmp_path, nb_images=0, seed=0)   # les 3 images de référence
    run(tmp_path, generate_data=False, nb_files=0, seed=0, delay=0)

    rows = conn.execute("SELECT montant, flag FROM transactions ORDER BY montant").fetchall()
    assert rows == [
        (Decimal("150.75"), False),
        (Decimal("5000.00"), False),   # pile 5000 -> pas de flag
        (Decimal("6200.00"), True),
    ]
    assert count(conn, "processed_files") == 3
    total_de = conn.execute(
        "SELECT total FROM received_by_iban WHERE iban = %s", (ACCOUNTS[2]["iban"],)
    ).fetchone()[0]
    assert total_de == Decimal("6200.00")


@needs_tesseract
def test_image_non_retraitee(conn, tmp_path):
    """Anti-doublons : une image déjà traitée n'est pas retraitée."""
    generate_images(tmp_path, nb_images=0, seed=0)
    run(tmp_path, generate_data=False, nb_files=0, seed=0, delay=0)
    run(tmp_path, generate_data=False, nb_files=0, seed=0, delay=0)
    assert count(conn, "processed_files") == 3
    assert count(conn, "transactions") == 3