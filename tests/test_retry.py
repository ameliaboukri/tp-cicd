"""Tests du mécanisme de retry (unitaires + intégration avec la base)."""
from decimal import Decimal

import pytest

from generator.generate_csv import reference_rows, write_csv
from pipeline.main import run
from pipeline.retry import RetryError, retry

IBAN_BNP = "FR7630006000011234567890189"


class Flaky:
    """Fonction qui échoue les N premières fois, puis réussit."""

    def __init__(self, failures):
        self.failures = failures
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.calls <= self.failures:
            raise ConnectionError(f"panne {self.calls}")
        return "ok"


# ---------- Tests unitaires ----------

def test_reussit_apres_echecs_temporaires():
    sleeps = []
    f = Flaky(2)
    result = retry(f, max_attempts=3, delay=1, retry_on=(ConnectionError,),
                   sleep=sleeps.append)
    assert result == "ok"
    assert f.calls == 3
    assert sleeps == [1, 2]   # on attend avant chaque nouvelle tentative (délai doublé)


def test_abandon_apres_nombre_max_de_tentatives():
    sleeps = []
    f = Flaky(10)
    with pytest.raises(RetryError, match="abandon après 3 tentatives"):
        retry(f, max_attempts=3, delay=1, retry_on=(ConnectionError,),
              sleep=sleeps.append)
    assert f.calls == 3        # pas une tentative de plus
    assert sleeps == [1, 2]    # pas d'attente après la dernière tentative


def test_erreur_non_temporaire_pas_de_retry():
    f = Flaky(1)
    with pytest.raises(ConnectionError):
        retry(f, max_attempts=3, delay=0, retry_on=(TimeoutError,),
              sleep=lambda s: None)
    assert f.calls == 1


def test_erreurs_affichees(capsys):
    retry(Flaky(1), max_attempts=3, delay=0, retry_on=(ConnectionError,),
          sleep=lambda s: None)
    out = capsys.readouterr().out
    assert "tentative 1/3 échouée" in out
    assert "panne 1" in out
    assert "[RETRY]" in out


# ---------- Tests d'intégration (vraie base) ----------

def count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


@pytest.fixture
def reference_dir(tmp_path):
    write_csv(tmp_path / "transactions_000.csv", reference_rows())
    return tmp_path


def test_retry_insertion_reussit_sans_doublon(conn, reference_dir):
    """2 pannes simulées puis succès : données complètes, aucun doublon."""
    run(reference_dir, generate_data=False, nb_files=0, seed=0,
        max_attempts=3, delay=0, simulated_failures=2)
    assert count(conn, "processed_files") == 1
    assert count(conn, "transactions") == 6          # et pas 12 ou 18
    total = conn.execute(
        "SELECT total FROM sent_by_iban WHERE iban = %s", (IBAN_BNP,)
    ).fetchone()[0]
    assert total == Decimal("8500.50")


def test_retry_abandon_et_rollback(conn, reference_dir):
    """Pannes persistantes : la pipeline s'arrête et rien n'est inséré."""
    with pytest.raises(RetryError):
        run(reference_dir, generate_data=False, nb_files=0, seed=0,
            max_attempts=3, delay=0, simulated_failures=5)
    assert count(conn, "processed_files") == 0
    assert count(conn, "transactions") == 0
    assert count(conn, "sent_by_iban") == 0