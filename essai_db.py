from pipeline import db
from pipeline.loader import load_csv_file
from pipeline.processing import process

path = "data/transactions_000.csv"

conn = db.get_connection()
db.init_schema(conn)

file_hash = db.compute_hash(open(path, "rb").read())
if db.is_file_processed(conn, file_hash):
    print("Fichier déjà traité -> on ne le retraite pas")
else:
    results = process(load_csv_file(path))
    db.insert_results(conn, "transactions_000.csv", file_hash, results)
    print("Fichier inséré dans la base !")

conn.close()