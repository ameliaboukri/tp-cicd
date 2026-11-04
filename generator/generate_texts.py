"""Génère des fichiers texte décrivant des virements en langage naturel (pour le SLM)."""
import argparse
from pathlib import Path

# Textes de référence : résultats connus d'avance -> utilisés dans les tests
REFERENCE_TEXTS = [
    # L'exemple EXACT du sujet (pas d'année, pas de banque émettrice) -> flag (6200 > 5000)
    "Le 12 septembre à 14h30, le compte FR761234567890 a envoyé 6200 € vers le compte "
    "DE987654321 appartenant à une banque allemande.",
    # Montant au format français avec espace et virgule, banque nommée
    "Virement du 3 mars 2026 à 9h15 : Santander a transféré 1 250,50 € depuis le compte "
    "ES9121000418450200051332 vers le compte IT60X0542811101000000123456.",
    # Pile 5000 -> PAS de flag
    "Le 20 octobre 2026 à 18h05, BNP Paribas a viré 5000 euros du compte "
    "FR7630006000011234567890189 au compte BE68539007547034.",
]


def generate_texts(output_dir):
    """Écrit les textes de référence dans des fichiers texte_XXX.txt."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, text in enumerate(REFERENCE_TEXTS):
        path = output_dir / f"texte_{i:03d}.txt"
        path.write_text(text + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def main():
    parser = argparse.ArgumentParser(description="Génère des textes de virements")
    parser.add_argument("--output", default="data", help="Dossier de sortie")
    args = parser.parse_args()

    paths = generate_texts(args.output)
    print(f"{len(paths)} textes générés dans '{args.output}' :")
    for p in paths:
        print(f"  - {p.name} : {p.read_text(encoding='utf-8').strip()}")


if __name__ == "__main__":
    main()