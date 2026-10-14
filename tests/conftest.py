"""Fixtures pytest partagées."""
import pytest

from pipeline import db, storage

TABLES = "processed_files, transactions, sent_by_iban, sent_by_bank, received_by_iban"


def empty_bucket():
    """Supprime tous les CSV du bucket (pour repartir d'un S3 propre)."""
    s3 = storage.get_client()
    storage.ensure_bucket(s3)
    for key in storage.list_keys(s3):
        s3.delete_object(Bucket=storage.BUCKET, Key=key)


@pytest.fixture
def conn():
    """Base ET bucket S3 vidés avant chaque test d'intégration."""
    empty_bucket()
    connection = db.get_connection()
    db.init_schema(connection)
    connection.execute(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE")
    yield connection
    connection.close()