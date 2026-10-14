"""Tests unitaires : traitements purs et validation du loader."""
import copy
from datetime import datetime
from decimal import Decimal

import pytest

from pipeline.loader import InvalidCSVError, parse_csv_text
from pipeline.processing import (
    flag_transactions,
    process,
    sum_received_by_iban,
    sum_sent_by_bank,
    sum_sent_by_iban,
)


def tx(origine, banque, dest, montant):
    return {
        "datetime_transaction": datetime(2026, 1, 1, 12, 0),
        "iban_origine": origine,
        "pays_source": "France",
        "banque_source": banque,
        "iban_destinataire": dest,
        "pays_destinataire": "France",
        "montant": Decimal(montant),
    }


SAMPLE = [
    tx("A", "Banque1", "B", "100.00"),
    tx("A", "Banque1", "C", "50.50"),
    tx("B", "Banque2", "A", "6000.00"),
    tx("C", "Banque1", "B", "5000.00"),
]

HEADER = ("datetime_transaction,iban_origine,pays_source,banque_source,"
          "iban_destinataire,pays_destinataire,montant\n")


def test_sum_sent_by_iban():
    assert sum_sent_by_iban(SAMPLE) == {
        "A": Decimal("150.50"), "B": Decimal("6000.00"), "C": Decimal("5000.00")}


def test_sum_sent_by_bank():
    assert sum_sent_by_bank(SAMPLE) == {
        "Banque1": Decimal("5150.50"), "Banque2": Decimal("6000.00")}


def test_sum_received_by_iban():
    assert sum_received_by_iban(SAMPLE) == {
        "B": Decimal("5100.00"), "C": Decimal("50.50"), "A": Decimal("6000.00")}


def test_flag_strictement_superieur_a_5000():
    flags = [t["flag"] for t in flag_transactions(SAMPLE)]
    assert flags == [False, False, True, False]  # 5000.00 pile -> pas de flag


def test_fonctions_pures():
    original = copy.deepcopy(SAMPLE)
    r1 = process(SAMPLE)
    r2 = process(SAMPLE)
    assert SAMPLE == original          # l'entrée n'est pas modifiée
    assert "flag" not in SAMPLE[0]     # le flag est sur une copie
    assert r1 == r2                    # même entrée -> même résultat


def test_loader_montant_invalide():
    with pytest.raises(InvalidCSVError, match="montant invalide"):
        parse_csv_text(HEADER + "2026-01-01 10:00:00,A,France,B1,B,France,abc\n")


def test_loader_montant_negatif():
    with pytest.raises(InvalidCSVError, match="doit être > 0"):
        parse_csv_text(HEADER + "2026-01-01 10:00:00,A,France,B1,B,France,-5\n")


def test_loader_date_invalide():
    with pytest.raises(InvalidCSVError, match="date invalide"):
        parse_csv_text(HEADER + "pas-une-date,A,France,B1,B,France,10\n")


def test_loader_colonne_manquante():
    with pytest.raises(InvalidCSVError, match="colonnes manquantes"):
        parse_csv_text("datetime_transaction,montant\n2026-01-01 10:00:00,10\n")