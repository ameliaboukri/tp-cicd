from pathlib import Path

from pipeline import storage

client = storage.get_client()
print("Bucket créé :", storage.ensure_bucket(client))

paths = sorted(Path("data").glob("*.csv"))
keys = storage.upload_files(client, paths)
print("Envoyés :", keys)

storage.verify_uploaded(client, keys)
print("Présents dans le S3 :", storage.list_csv_keys(client))

content = storage.download_bytes(client, keys[0])
print("Début de", keys[0], ":", content[:80])