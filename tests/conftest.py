"""Fixtures pytest partagées."""
import pytest

from pipeline import db

TABLES = "processed_files, transactions, sent_by_iban, sent_by_bank, received_by_iban"


@pytest.fixture
def conn():
    """Connexion à une base propre (tables vidées avant chaque test)."""
    connection = db.get_connection()
    db.init_schema(connection)
    connection.execute(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE")
    yield connection
    connection.close()