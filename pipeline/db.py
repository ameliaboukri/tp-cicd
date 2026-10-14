"""Accès à la base PostgreSQL : schéma, anti-doublons et insertion."""
import hashlib
import os
from pathlib import Path

import psycopg

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"


def get_connection():
    """Connexion à la base (paramètres lus dans les variables d'environnement)."""
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER", "pipeline"),
        password=os.getenv("DB_PASSWORD", "pipeline"),
        dbname=os.getenv("DB_NAME", "transactions"),
        autocommit=True,  # les transactions sont gérées explicitement
    )


def init_schema(conn):
    """Crée les tables si elles n'existent pas encore."""
    conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))


def compute_hash(content):
    """Empreinte SHA-256 du contenu brut (bytes) d'un fichier."""
    return hashlib.sha256(content).hexdigest()


def is_file_processed(conn, file_hash):
    """True si un fichier avec ce contenu a déjà été traité avec succès."""
    row = conn.execute(
        "SELECT 1 FROM processed_files WHERE file_hash = %s", (file_hash,)
    ).fetchone()
    return row is not None


def _upsert_totals(cur, table, key_column, totals):
    """Ajoute les sommes au total existant (ou crée la ligne si nouvelle)."""
    cur.executemany(
        f"INSERT INTO {table} ({key_column}, total) VALUES (%s, %s) "
        f"ON CONFLICT ({key_column}) DO UPDATE SET total = {table}.total + EXCLUDED.total",
        list(totals.items()),
    )


def insert_results(conn, file_name, file_hash, results):
    """Insère les résultats d'un fichier en UNE transaction (tout ou rien)."""
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO processed_files (file_name, file_hash, nb_transactions) "
                "VALUES (%s, %s, %s) RETURNING id",
                (file_name, file_hash, len(results["transactions"])),
            )
            file_id = cur.fetchone()[0]

            cur.executemany(
                "INSERT INTO transactions (file_id, datetime_transaction, iban_origine, "
                "pays_source, banque_source, iban_destinataire, pays_destinataire, "
                "montant, flag) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [
                    (
                        file_id,
                        t["datetime_transaction"],
                        t["iban_origine"],
                        t["pays_source"],
                        t["banque_source"],
                        t["iban_destinataire"],
                        t["pays_destinataire"],
                        t["montant"],
                        t["flag"],
                    )
                    for t in results["transactions"]
                ],
            )

            _upsert_totals(cur, "sent_by_iban", "iban", results["sent_by_iban"])
            _upsert_totals(cur, "sent_by_bank", "banque", results["sent_by_bank"])
            _upsert_totals(cur, "received_by_iban", "iban", results["received_by_iban"])
    return file_id