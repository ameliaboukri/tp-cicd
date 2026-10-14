"""Génère des images d'ordres de virement (pour tester l'OCR) - données déterministes."""
import argparse
import random
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from generator.generate_csv import ACCOUNTS

# Virements de référence : (date, index émetteur, index destinataire, montant)
# Résultats connus d'avance -> utilisés dans les tests
REFERENCE_IMAGES = [
    ("2026-09-12 14:30:00", 0, 2, 6200.00),   # exemple du sujet : FR -> DE, 6200 EUR -> flag
    ("2026-09-13 09:00:00", 3, 4, 5000.00),   # pile 5000 -> PAS de flag
    ("2026-09-14 17:45:00", 5, 1, 150.75),
]

FONT_SIZE = 32
MARGIN = 40
LINE_SPACING = 18


def image_lines(dt_str, origin, dest, amount):
    """Texte de l'ordre de virement, une information par ligne (sans accents)."""
    return [
        "ORDRE DE VIREMENT",
        "",
        f"Date : {dt_str}",
        f"IBAN emetteur : {origin['iban']}",
        f"Pays emetteur : {origin['pays']}",
        f"Banque emettrice : {origin['banque']}",
        f"IBAN destinataire : {dest['iban']}",
        f"Pays destinataire : {dest['pays']}",
        f"Montant : {amount:.2f} EUR",
    ]


def render_image(lines, path):
    """Dessine les lignes en noir sur fond blanc et enregistre le PNG."""
    font = ImageFont.load_default(size=FONT_SIZE)
    line_height = FONT_SIZE + LINE_SPACING
    width = 1200
    height = MARGIN * 2 + line_height * len(lines)

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    y = MARGIN
    for line in lines:
        draw.text((MARGIN, y), line, fill="black", font=font)
        y += line_height
    image.save(path)


def generate_images(output_dir, nb_images, seed):
    """Génère les images de référence + nb_images images pseudo-aléatoires."""
    rng = random.Random(seed)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    specs = [(dt, ACCOUNTS[o], ACCOUNTS[d], amount)
             for dt, o, d, amount in REFERENCE_IMAGES]

    base = datetime(2026, 9, 1, 8, 0, 0)
    for _ in range(nb_images):
        origin, dest = rng.sample(ACCOUNTS, 2)
        dt = base + timedelta(minutes=rng.randint(0, 60 * 24 * 30))
        amount = round(rng.uniform(10, 9000), 2)
        specs.append((dt.strftime("%Y-%m-%d %H:%M:%S"), origin, dest, amount))

    paths = []
    for i, (dt, origin, dest, amount) in enumerate(specs):
        path = output_dir / f"virement_{i:03d}.png"
        render_image(image_lines(dt, origin, dest, amount), path)
        paths.append(path)
    return paths


def main():
    parser = argparse.ArgumentParser(description="Génère des images de virements")
    parser.add_argument("--output", default="data", help="Dossier de sortie")
    parser.add_argument("--images", type=int, default=2, help="Nb d'images aléatoires")
    parser.add_argument("--seed", type=int, default=42, help="Graine aléatoire")
    args = parser.parse_args()

    paths = generate_images(args.output, args.images, args.seed)
    print(f"{len(paths)} images générées dans '{args.output}' :")
    for p in paths:
        print(f"  - {p.name}")


if __name__ == "__main__":
    main()