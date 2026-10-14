"""Tests d'intégration : pipeline complète + vérifications en base."""
import csv
from datetime import datetime
from decimal import Decimal

import pytest

from generator.generate_csv import generate, reference_rows, write_csv
from pipeline.main import run

IBAN_BNP = "FR7630006000011234567890189"
IBAN_DE = "DE89370400440532013000"
IBAN_ES = "ES9121000418450200051332"


@pytest.fixture
def reference_dir(tmp_path):
    """Dossier temporaire contenant uniquement le fichier de référence."""
    write_csv(tmp_path / "transactions_000.csv", reference_rows())
    return tmp_path


def run_pipeline(data_dir):
    run(data_dir, generate_data=False, nb_files=0, seed=0)


def count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def totals(conn, table, key):
    return dict(conn.execute(f"SELECT {key}, total FROM {table}").fetchall())


def test_donnees_inserees(conn, reference_dir):
    run_pipeline(reference_dir)
    assert count(conn, "transactions") == 6
    assert count(conn, "processed_files") == 1


def test_valeurs_enregistrees(conn, reference_dir):
    run_pipeline(reference_dir)
    row = conn.execute(
        "SELECT datetime_transaction, iban_origine, pays_source, banque_source, "
        "iban_destinataire, pays_destinataire, montant "
        "FROM transactions WHERE montant = 2500.50"
    ).fetchone()
    assert row == (datetime(2026, 1, 10, 10, 30), IBAN_BNP, "France", "BNP Paribas",
                   IBAN_ES, "Espagne", Decimal("2500.50"))


def test_sommes(conn, reference_dir):
    run_pipeline(reference_dir)
    assert totals(conn, "sent_by_iban", "iban")[IBAN_BNP] == Decimal("8500.50")
    assert totals(conn, "received_by_iban", "iban")[IBAN_DE] == Decimal("6200.00")
    assert totals(conn, "sent_by_bank", "banque") == {
        "BNP Paribas": Decimal("8500.50"),
        "Deutsche Bank": Decimal("5000.01"),
        "Santander": Decimal("7500.00"),
        "UniCredit": Decimal("200.00"),
    }


def test_flags(conn, reference_dir):
    run_pipeline(reference_dir)
    rows = conn.execute("SELECT montant, flag FROM transactions ORDER BY montant").fetchall()
    flags = dict(rows)
    assert flags[Decimal("5000.00")] is False   # pile 5000 -> pas de flag
    assert flags[Decimal("5000.01")] is True
    assert [m for m, f in rows if f] == [Decimal("5000.01"), Decimal("7500.00")]


def test_pas_de_double_traitement(conn, reference_dir):
    run_pipeline(reference_dir)
    run_pipeline(reference_dir)   # 2e passage : le fichier doit être ignoré
    assert count(conn, "transactions") == 6
    assert count(conn, "processed_files") == 1
    assert totals(conn, "sent_by_iban", "iban")[IBAN_BNP] == Decimal("8500.50")


def test_plusieurs_fichiers_coherents(conn, tmp_path):
    """Sommes en base == sommes recalculées directement depuis les CSV bruts."""
    generate(tmp_path, nb_files=3, seed=123)
    run_pipeline(tmp_path)

    expected, nb_rows = {}, 0
    for path in tmp_path.glob("*.csv"):
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                iban = row["iban_origine"]
                expected[iban] = expected.get(iban, Decimal("0")) + Decimal(row["montant"])
                nb_rows += 1

    assert count(conn, "transactions") == nb_rows
    assert totals(conn, "sent_by_iban", "iban") == expected