"""Pipeline complète : génération -> base -> chargement -> traitement -> insertion."""
import argparse
import os
import sys
from pathlib import Path

import psycopg

from generator.generate_csv import generate
from pipeline import db
from pipeline.loader import load_csv_file
from pipeline.processing import process
from pipeline.retry import retry

# Erreurs considérées comme temporaires -> on réessaie
RETRYABLE_ERRORS = (psycopg.OperationalError, db.TransientDBError)

# La base peut mettre quelques secondes à démarrer : on laisse plus de tentatives
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


def process_file(conn, path, max_attempts, delay, simulator):
    """Traite un fichier s'il ne l'a pas déjà été. Renvoie True si inséré."""
    file_hash = db.compute_hash(path.read_bytes())
    if db.is_file_processed(conn, file_hash):
        print(f"  [SKIP] {path.name} déjà traité")
        return False

    transactions = load_csv_file(path)
    results = process(transactions)

    inserted = retry(
        lambda: insert_once(path.name, file_hash, results, simulator),
        max_attempts=max_attempts,
        delay=delay,
        retry_on=RETRYABLE_ERRORS,
        label=f"insertion de {path.name}",
    )
    if not inserted:
        print(f"  [SKIP] {path.name} déjà présent en base")
        return False

    nb_flags = sum(t["flag"] for t in results["transactions"])
    print(f"  [OK]   {path.name} : {len(transactions)} transactions, {nb_flags} flag(s)")
    return True


def run(data_dir, generate_data, nb_files, seed,
        max_attempts=3, delay=1.0, simulated_failures=0):
    data_dir = Path(data_dir)

    if generate_data:
        print("[1/3] Génération des fichiers CSV")
        generate(data_dir, nb_files, seed)
    else:
        print("[1/3] Génération ignorée (--no-generate)")

    print("[2/3] Mise en place de la base de données")
    conn = retry(
        db.get_connection,
        max_attempts=CONNECT_ATTEMPTS,
        delay=delay,
        retry_on=(psycopg.OperationalError,),
        label="connexion à la base",
    )
    try:
        db.init_schema(conn)

        print("[3/3] Chargement, traitement et insertion "
              f"(max {max_attempts} tentatives par fichier)")
        simulator = db.FailureSimulator(simulated_failures)
        if simulated_failures:
            print(f"  /!\\ SIMULATION : les {simulated_failures} prochaine(s) "
                  "tentative(s) d'insertion vont échouer")

        files = sorted(data_dir.glob("*.csv"))
        if not files:
            raise RuntimeError(f"Aucun fichier CSV trouvé dans '{data_dir}'")

        inserted = sum(
            process_file(conn, path, max_attempts, delay, simulator) for path in files
        )
        print(f"Terminé : {inserted} fichier(s) inséré(s), "
              f"{len(files) - inserted} ignoré(s) (déjà traités)")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Pipeline data de transactions")
    parser.add_argument("--data-dir", default="data", help="Dossier des CSV")
    parser.add_argument("--no-generate", action="store_true", help="Ne pas générer de CSV")
    parser.add_argument("--files", type=int, default=4, help="Nb de fichiers à générer")
    parser.add_argument("--seed", type=int, default=42, help="Graine aléatoire")
    parser.add_argument("--max-retries", type=int,
                        default=int(os.getenv("DB_MAX_RETRIES", "3")),
                        help="Nb max de tentatives d'insertion par fichier")
    parser.add_argument("--retry-delay", type=float,
                        default=float(os.getenv("DB_RETRY_DELAY", "1.0")),
                        help="Délai avant la 2e tentative (secondes)")
    parser.add_argument("--simulate-db-failures", type=int,
                        default=int(os.getenv("SIMULATE_DB_FAILURES", "0")),
                        help="Nb de pannes d'insertion à simuler")
    args = parser.parse_args()

    try:
        run(args.data_dir, not args.no_generate, args.files, args.seed,
            args.max_retries, args.retry_delay, args.simulate_db_failures)
    except Exception as e:
        print(f"ERREUR pipeline : {e}", file=sys.stderr)
        sys.exit(1)  # code d'erreur -> la CI passera en rouge


if __name__ == "__main__":
    main()