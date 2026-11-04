"""Tests de l'option 3 : extraction de transactions depuis du texte avec un SLM."""
import os
import urllib.request
from datetime import datetime
from decimal import Decimal

import pytest

from generator.generate_texts import REFERENCE_TEXTS, generate_texts
from pipeline import slm
from pipeline.main import run
from pipeline.slm import SLMExtractionError, to_row

TEXTE_SUJET = REFERENCE_TEXTS[0]   

# Réponse JSON réellement renvoyée par qwen2.5:1.5b pour l'exemple du sujet
REPONSE_SUJET = {
    "jour": 12, "mois": 9, "annee": 0, "heure": 14, "minute": 30,
    "iban_origine": "FR761234567890", "banque_source": "",
    "iban_destinataire": "DE987654321", "montant": 6200,
}


def ollama_available():
    try:
        urllib.request.urlopen(f"{slm.OLLAMA_URL}/api/tags", timeout=2)
        return True
    except Exception:
        return False


# En CI (REQUIRE_SLM=1), on ne saute jamais : un Ollama absent doit faire échouer
REQUIRE_SLM = os.getenv("REQUIRE_SLM") == "1"
needs_slm = pytest.mark.skipif(not REQUIRE_SLM and not ollama_available(),
                               reason="Ollama non démarré")


def count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# ---------- Tests unitaires (sans modèle) : validation / transformation ----------

def test_transformation_exemple_du_sujet():
    row = to_row(REPONSE_SUJET, TEXTE_SUJET)
    assert row == {
        "datetime_transaction": "2026-09-12 14:30:00",   # année absente -> 2026
        "iban_origine": "FR761234567890",
        "pays_source": "France",                          # déduit de "FR"
        "banque_source": "Inconnue",                      # non nommée dans le texte
        "iban_destinataire": "DE987654321",
        "pays_destinataire": "Allemagne",                 # déduit de "DE"
        "montant": "6200.00",
    }


def test_garde_fou_montant_invente():
    with pytest.raises(SLMExtractionError, match="montant 6300.00 absent du texte"):
        to_row({**REPONSE_SUJET, "montant": 6300}, TEXTE_SUJET)


def test_garde_fou_iban_invente():
    with pytest.raises(SLMExtractionError, match="absent du texte"):
        to_row({**REPONSE_SUJET, "iban_destinataire": "DE987654329"}, TEXTE_SUJET)


def test_garde_fou_emetteur_egal_destinataire():
    with pytest.raises(SLMExtractionError, match="identiques"):
        to_row({**REPONSE_SUJET, "iban_destinataire": "FR761234567890"}, TEXTE_SUJET)


def test_reponse_incomplete():
    reponse = {k: v for k, v in REPONSE_SUJET.items() if k != "montant"}
    with pytest.raises(SLMExtractionError, match="incomplète"):
        to_row(reponse, TEXTE_SUJET)


# ---------- Tests avec le vrai modèle (Ollama) ----------

@needs_slm
def test_slm_exemple_du_sujet():
    [t] = slm.extract_transactions(TEXTE_SUJET.encode("utf-8"), "sujet")
    assert t["datetime_transaction"] == datetime(2026, 9, 12, 14, 30)
    assert t["iban_origine"] == "FR761234567890"
    assert t["iban_destinataire"] == "DE987654321"
    assert t["pays_destinataire"] == "Allemagne"
    assert t["montant"] == Decimal("6200.00")


@needs_slm
def test_textes_dans_la_pipeline(conn, tmp_path):
    """Texte -> S3 -> SLM -> traitement -> base, avec les bons flags, sans doublon."""
    generate_texts(tmp_path)
    run(tmp_path, generate_data=False, nb_files=0, seed=0, delay=0)
    run(tmp_path, generate_data=False, nb_files=0, seed=0, delay=0)   

    rows = conn.execute("SELECT montant, flag FROM transactions ORDER BY montant").fetchall()
    assert rows == [
        (Decimal("1250.50"), False),
        (Decimal("5000.00"), False),   
        (Decimal("6200.00"), True),
    ]
    assert count(conn, "processed_files") == 3