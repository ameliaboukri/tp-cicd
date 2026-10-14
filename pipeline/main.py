"""Pipeline complète : génération -> base -> chargement -> traitement -> insertion."""
import argparse
import sys
from pathlib import Path

from generator.generate_csv import generate
from pipeline import db
from pipeline.loader import load_csv_file
from pipeline.processing import process


def process_file(conn, path):
    """Traite un fichier s'il ne l'a pas déjà été. Renvoie True si inséré."""
    file_hash = db.compute_hash(path.read_bytes())
    if db.is_file_processed(conn, file_hash):
        print(f"  [SKIP] {path.name} déjà traité")
        return False

    transactions = load_csv_file(path)
    results = process(transactions)
    db.insert_results(conn, path.name, file_hash, results)

    nb_flags = sum(t["flag"] for t in results["transactions"])
    print(f"  [OK]   {path.name} : {len(transactions)} transactions, {nb_flags} flag(s)")
    return True


def run(data_dir, generate_data, nb_files, seed):
    data_dir = Path(data_dir)

    if generate_data:
        print("[1/3] Génération des fichiers CSV")
        generate(data_dir, nb_files, seed)
    else:
        print("[1/3] Génération ignorée (--no-generate)")

    print("[2/3] Mise en place de la base de données")
    conn = db.get_connection()
    try:
        db.init_schema(conn)

        print("[3/3] Chargement, traitement et insertion")
        files = sorted(data_dir.glob("*.csv"))
        if not files:
            raise RuntimeError(f"Aucun fichier CSV trouvé dans '{data_dir}'")

        inserted = sum(process_file(conn, path) for path in files)
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
    args = parser.parse_args()

    try:
        run(args.data_dir, not args.no_generate, args.files, args.seed)
    except Exception as e:
        print(f"ERREUR pipeline : {e}", file=sys.stderr)
        sys.exit(1)  # code d'erreur -> la CI passera en rouge


if __name__ == "__main__":
    main()