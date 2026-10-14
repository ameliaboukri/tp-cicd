"""Pipeline complète : génération -> S3 -> chargement -> traitement -> base de données."""
import argparse
import os
import sys
from pathlib import Path

import psycopg
from botocore.exceptions import ConnectionError as BotoConnectionError
from botocore.exceptions import HTTPClientError

from generator.generate_csv import generate
from pipeline import db, storage
from pipeline.loader import parse_csv_text
from pipeline.processing import process
from pipeline.retry import retry

# Erreurs considérées comme temporaires -> on réessaie
DB_RETRYABLE = (psycopg.OperationalError, db.TransientDBError)
# Connexion impossible / timeout de connexion (BotoConnectionError),
# coupure ou timeout de lecture (HTTPClientError), panne simulée
S3_RETRYABLE = (BotoConnectionError, HTTPClientError, storage.TransientS3Error)

# Les services peuvent mettre quelques secondes à démarrer : on laisse plus de tentatives
CONNECT_ATTEMPTS = 5


def insert_once(file_name, file_hash, results, simulator):
    """UNE tentative d'insertion, avec une connexion neuve à chaque fois."""
    with db.get_connection() as conn:
        if db.is_file_processed(conn, file_hash):
            return False  # déjà inséré (ex : tentative précédente réussie)
        try:
            db.insert_results(conn, file_name, file_hash, results, simulator)
        except psycopg.errors.UniqueViolation:
            return False  # filet de sécurité : hash déjà présent en base
        return True


def process_key(conn, s3, key, max_attempts, delay, db_simulator, s3_simulator):
    """Récupère un fichier du S3 et le traite s'il ne l'a pas déjà été."""
    content = retry(
        lambda: storage.download_bytes(s3, key, simulator=s3_simulator),
        max_attempts=max_attempts,
        delay=delay,
        retry_on=S3_RETRYABLE,
        label=f"récupération de {key} depuis le S3",
    )

    file_hash = db.compute_hash(content)
    if db.is_file_processed(conn, file_hash):
        print(f"  [SKIP] {key} déjà traité")
        return False

    transactions = parse_csv_text(content.decode("utf-8-sig"), source=key)
    results = process(transactions)

    inserted = retry(
        lambda: insert_once(key, file_hash, results, db_simulator),
        max_attempts=max_attempts,
        delay=delay,
        retry_on=DB_RETRYABLE,
        label=f"insertion de {key}",
    )
    if not inserted:
        print(f"  [SKIP] {key} déjà présent en base")
        return False

    nb_flags = sum(t["flag"] for t in results["transactions"])
    print(f"  [OK]   {key} : {len(transactions)} transactions, {nb_flags} flag(s)")
    return True


def run(data_dir, generate_data, nb_files, seed, max_attempts=3, delay=1.0,
        simulated_failures=0, simulated_s3_failures=0):
    data_dir = Path(data_dir)

    print("[1/5] Connexion au S3 et préparation du bucket")
    s3 = storage.get_client()
    created = retry(
        lambda: storage.ensure_bucket(s3),
        max_attempts=CONNECT_ATTEMPTS,
        delay=delay,
        retry_on=S3_RETRYABLE,
        label="connexion au S3",
    )
    print(f"  bucket '{storage.BUCKET}' {'créé' if created else 'déjà existant'}")

    if generate_data:
        print("[2/5] Génération des fichiers CSV")
        generate(data_dir, nb_files, seed)
    else:
        print("[2/5] Génération ignorée (--no-generate)")

    print("[3/5] Envoi des CSV dans le S3 et vérification")
    local_files = sorted(data_dir.glob("*.csv")) if data_dir.exists() else []
    keys = storage.upload_files(s3, local_files)
    storage.verify_uploaded(s3, keys)
    print(f"  {len(keys)} fichier(s) envoyé(s) et présent(s) dans le S3")

    print("[4/5] Mise en place de la base de données")
    conn = retry(
        db.get_connection,
        max_attempts=CONNECT_ATTEMPTS,
        delay=delay,
        retry_on=(psycopg.OperationalError,),
        label="connexion à la base",
    )
    try:
        db.init_schema(conn)

        print("[5/5] Récupération depuis le S3, chargement, traitement et insertion "
              f"(max {max_attempts} tentatives)")
        db_simulator = db.FailureSimulator(simulated_failures)
        s3_simulator = storage.S3FailureSimulator(simulated_s3_failures)
        if simulated_failures:
            print(f"  /!\\ SIMULATION : les {simulated_failures} prochaine(s) "
                  "tentative(s) d'insertion vont échouer")
        if simulated_s3_failures:
            print(f"  /!\\ SIMULATION : les {simulated_s3_failures} prochaine(s) "
                  "récupération(s) S3 vont échouer")

        s3_keys = storage.list_csv_keys(s3)
        if not s3_keys:
            print("  Aucun fichier à traiter dans le S3")
            return

        inserted = sum(
            process_key(conn, s3, key, max_attempts, delay, db_simulator, s3_simulator)
            for key in s3_keys
        )
        print(f"Terminé : {inserted} fichier(s) inséré(s), "
              f"{len(s3_keys) - inserted} ignoré(s) (déjà traités)")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Pipeline data de transactions")
    parser.add_argument("--data-dir", default="data", help="Dossier local de génération")
    parser.add_argument("--no-generate", action="store_true", help="Ne pas générer de CSV")
    parser.add_argument("--files", type=int, default=4, help="Nb de fichiers à générer")
    parser.add_argument("--seed", type=int, default=42, help="Graine aléatoire")
    parser.add_argument("--max-retries", type=int,
                        default=int(os.getenv("MAX_RETRIES", "3")),
                        help="Nb max de tentatives (insertion et récupération S3)")
    parser.add_argument("--retry-delay", type=float,
                        default=float(os.getenv("RETRY_DELAY", "1.0")),
                        help="Délai avant la 2e tentative (secondes)")
    parser.add_argument("--simulate-db-failures", type=int,
                        default=int(os.getenv("SIMULATE_DB_FAILURES", "0")),
                        help="Nb de pannes d'insertion à simuler")
    parser.add_argument("--simulate-s3-failures", type=int,
                        default=int(os.getenv("SIMULATE_S3_FAILURES", "0")),
                        help="Nb de pannes de récupération S3 à simuler")
    args = parser.parse_args()

    try:
        run(args.data_dir, not args.no_generate, args.files, args.seed,
            args.max_retries, args.retry_delay,
            args.simulate_db_failures, args.simulate_s3_failures)
    except Exception as e:
        print(f"ERREUR pipeline : {e}", file=sys.stderr)
        sys.exit(1)  # code d'erreur -> la CI passera en rouge


if __name__ == "__main__":
    main()