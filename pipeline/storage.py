"""Accès au stockage S3 (SeaweedFS en local, compatible avec n'importe quel S3)."""
import os
from pathlib import Path

import boto3
from botocore.config import Config

BUCKET = os.getenv("S3_BUCKET", "transactions")
PREFIX = "incoming/"   # « dossier » où sont déposés les CSV à traiter


class TransientS3Error(Exception):
    """Erreur temporaire du S3 (utilisée pour la simulation)."""


class S3FailureSimulator:
    """Fait échouer volontairement les N prochains téléchargements (pour tester le retry)."""

    def __init__(self, nb_failures=0):
        self.remaining = nb_failures

    def maybe_fail(self, key):
        if self.remaining > 0:
            self.remaining -= 1
            raise TransientS3Error(f"panne simulée : S3 indisponible (timeout) pour {key}")


def get_client():
    """Client S3 (paramètres lus dans les variables d'environnement)."""
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT", "http://localhost:8333"),
        aws_access_key_id=os.getenv("S3_ACCESS_KEY", "admin"),
        aws_secret_access_key=os.getenv("S3_SECRET_KEY", "admin123"),
        region_name="us-east-1",
        config=Config(
            s3={"addressing_style": "path"},      # http://host/bucket/cle
            retries={"max_attempts": 1},          # pas de retry caché : on gère le nôtre
            connect_timeout=3,
            read_timeout=5,
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def ensure_bucket(client, bucket=BUCKET):
    """Crée le bucket s'il n'existe pas. Renvoie True s'il vient d'être créé."""
    try:
        client.create_bucket(Bucket=bucket)
        return True
    except (client.exceptions.BucketAlreadyOwnedByYou,
            client.exceptions.BucketAlreadyExists):
        return False   # il existe déjà : rien à faire


def upload_files(client, paths, bucket=BUCKET):
    """Envoie des fichiers locaux dans le bucket. Renvoie la liste des clés S3."""
    keys = []
    for path in paths:
        key = PREFIX + Path(path).name
        client.upload_file(str(path), bucket, key)
        keys.append(key)
    return keys


def list_csv_keys(client, bucket=BUCKET):
    """Liste (triée) des fichiers CSV présents dans le bucket."""
    keys = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=PREFIX):
        keys += [obj["Key"] for obj in page.get("Contents", []) if obj["Key"].endswith(".csv")]
    return sorted(keys)


def verify_uploaded(client, keys, bucket=BUCKET):
    """Vérifie que tous les fichiers envoyés sont bien présents dans le S3."""
    present = set(list_csv_keys(client, bucket))
    missing = [k for k in keys if k not in present]
    if missing:
        raise RuntimeError(f"Fichiers absents du S3 après l'upload : {missing}")


def download_bytes(client, key, bucket=BUCKET, simulator=None):
    """Télécharge le contenu brut (bytes) d'un fichier du S3."""
    if simulator is not None:
        simulator.maybe_fail(key)
    response = client.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()