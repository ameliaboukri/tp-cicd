"""Génère des fichiers CSV de transactions financières (données déterministes)."""
import argparse
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

COLUMNS = [
    "datetime_transaction",
    "iban_origine",
    "pays_source",
    "banque_source",
    "iban_destinataire",
    "pays_destinataire",
    "montant",
]

# Comptes fixes : chaque IBAN a toujours le même pays et la même banque
ACCOUNTS = [
    {"iban": "FR7630006000011234567890189", "pays": "France", "banque": "BNP Paribas"},
    {"iban": "FR7630003000031234567890143", "pays": "France", "banque": "Societe Generale"},
    {"iban": "DE89370400440532013000", "pays": "Allemagne", "banque": "Deutsche Bank"},
    {"iban": "ES9121000418450200051332", "pays": "Espagne", "banque": "Santander"},
    {"iban": "IT60X0542811101000000123456", "pays": "Italie", "banque": "UniCredit"},
    {"iban": "BE68539007547034", "pays": "Belgique", "banque": "ING Belgique"},
]

# Fichier de référence : (date, index émetteur, index destinataire, montant)
# Résultats connus d'avance -> utilisés dans les tests
REFERENCE_TRANSACTIONS = [
    ("2026-01-10 09:15:00", 0, 2, 1000.00),
    ("2026-01-10 10:30:00", 0, 3, 2500.50),
    ("2026-01-11 14:00:00", 0, 2, 5000.00),  # pile 5000 -> PAS de flag
    ("2026-01-12 16:45:00", 2, 0, 5000.01),  # > 5000 -> flag
    ("2026-01-13 08:20:00", 3, 4, 7500.00),  # > 5000 -> flag
    ("2026-01-14 11:05:00", 4, 2, 200.00),
]


def make_row(dt_str, origin, dest, amount):
    """Construit une ligne CSV à partir de deux comptes et d'un montant."""
    return {
        "datetime_transaction": dt_str,
        "iban_origine": origin["iban"],
        "pays_source": origin["pays"],
        "banque_source": origin["banque"],
        "iban_destinataire": dest["iban"],
        "pays_destinataire": dest["pays"],
        "montant": f"{amount:.2f}",
    }


def reference_rows():
    """Transactions écrites à la main, aux résultats connus."""
    return [
        make_row(dt, ACCOUNTS[o], ACCOUNTS[d], amount)
        for dt, o, d, amount in REFERENCE_TRANSACTIONS
    ]


def random_rows(rng, count):
    """Transactions pseudo-aléatoires (reproductibles grâce à la graine)."""
    base = datetime(2026, 2, 1, 8, 0, 0)
    rows = []
    for _ in range(count):
        origin, dest = rng.sample(ACCOUNTS, 2)  # émetteur != destinataire
        dt = base + timedelta(minutes=rng.randint(0, 60 * 24 * 90))
        amount = round(rng.uniform(10, 9000), 2)
        rows.append(make_row(dt.strftime("%Y-%m-%d %H:%M:%S"), origin, dest, amount))
    rows.sort(key=lambda r: r["datetime_transaction"])
    return rows


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def generate(output_dir, nb_files, seed):
    """Génère le fichier de référence + nb_files fichiers pseudo-aléatoires."""
    rng = random.Random(seed)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = []
    ref_path = output_dir / "transactions_000.csv"
    write_csv(ref_path, reference_rows())
    paths.append(ref_path)

    for i in range(1, nb_files + 1):
        rows = random_rows(rng, rng.randint(5, 10))  # 5 à 10 transactions
        path = output_dir / f"transactions_{i:03d}.csv"
        write_csv(path, rows)
        paths.append(path)

    return paths


def main():
    parser = argparse.ArgumentParser(description="Génère des CSV de transactions")
    parser.add_argument("--output", default="data", help="Dossier de sortie")
    parser.add_argument("--files", type=int, default=4, help="Nb de fichiers aléatoires")
    parser.add_argument("--seed", type=int, default=42, help="Graine aléatoire")
    args = parser.parse_args()

    paths = generate(args.output, args.files, args.seed)
    print(f"{len(paths)} fichiers générés dans '{args.output}' :")
    for p in paths:
        print(f"  - {p.name}")


if __name__ == "__main__":
    main()