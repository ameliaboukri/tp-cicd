"""Tests d'intégration du stockage S3 et du retry de récupération."""
import shutil

import pytest

from generator.generate_csv import reference_rows, write_csv
from pipeline import storage
from pipeline.main import run
from pipeline.retry import RetryError


def count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


@pytest.fixture
def reference_dir(tmp_path):
    write_csv(tmp_path / "transactions_000.csv", reference_rows())
    return tmp_path


def test_upload_et_presence_dans_le_s3(conn, reference_dir):
    run(reference_dir, generate_data=False, nb_files=0, seed=0, delay=0)
    s3 = storage.get_client()
    assert storage.list_csv_keys(s3) == ["incoming/transactions_000.csv"]


def test_verification_detecte_un_fichier_manquant(conn):
    s3 = storage.get_client()
    with pytest.raises(RuntimeError, match="absents du S3"):
        storage.verify_uploaded(s3, ["incoming/fichier_fantome.csv"])


def test_traitement_ne_depend_pas_du_local(conn, reference_dir, tmp_path_factory):
    """Les fichiers sont lus depuis le S3, même si le dossier local est vide."""
    s3 = storage.get_client()
    storage.upload_files(s3, sorted(reference_dir.glob("*.csv")))
    shutil.rmtree(reference_dir)                      # plus aucun fichier local
    empty_dir = tmp_path_factory.mktemp("vide")
    run(empty_dir, generate_data=False, nb_files=0, seed=0, delay=0)
    assert count(conn, "transactions") == 6


def test_anti_doublon_par_contenu(conn, reference_dir):
    """Même contenu sous un autre nom : traité une seule fois (hash)."""
    shutil.copy(reference_dir / "transactions_000.csv",
                reference_dir / "transactions_999.csv")
    run(reference_dir, generate_data=False, nb_files=0, seed=0, delay=0)
    assert count(conn, "processed_files") == 1
    assert count(conn, "transactions") == 6


def test_retry_recuperation_s3_reussit(conn, reference_dir, capsys):
    run(reference_dir, generate_data=False, nb_files=0, seed=0,
        delay=0, simulated_s3_failures=2)
    out = capsys.readouterr().out
    assert "tentative 1/3 échouée" in out and "tentative 2/3 échouée" in out
    assert count(conn, "processed_files") == 1
    assert count(conn, "transactions") == 6


def test_retry_recuperation_s3_abandon(conn, reference_dir):
    with pytest.raises(RetryError, match="abandon après 3 tentatives"):
        run(reference_dir, generate_data=False, nb_files=0, seed=0,
            delay=0, simulated_s3_failures=5)
    assert count(conn, "processed_files") == 0
    assert count(conn, "transactions") == 0