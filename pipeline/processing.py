"""Traitements des transactions : uniquement des fonctions PURES.

Aucune fonction ici ne lit de fichier, ne touche à la base,
ni ne modifie les données reçues en entrée.
"""
from decimal import Decimal

FLAG_THRESHOLD = Decimal("5000")


def _sum_by(transactions, key):
    """Somme des montants groupés par la colonne `key` (nouveau dict)."""
    totals = {}
    for t in transactions:
        totals[t[key]] = totals.get(t[key], Decimal("0")) + t["montant"]
    return totals


def sum_sent_by_iban(transactions):
    """Somme des montants envoyés par iban_origine."""
    return _sum_by(transactions, "iban_origine")


def sum_sent_by_bank(transactions):
    """Somme des montants envoyés par banque_source."""
    return _sum_by(transactions, "banque_source")


def sum_received_by_iban(transactions):
    """Somme des montants reçus par iban_destinataire."""
    return _sum_by(transactions, "iban_destinataire")


def flag_transactions(transactions, threshold=FLAG_THRESHOLD):
    """Renvoie de NOUVELLES transactions avec un champ 'flag' (montant > seuil).

    {**t, ...} crée une copie : la transaction d'origine n'est pas modifiée.
    """
    return [{**t, "flag": t["montant"] > threshold} for t in transactions]


def process(transactions):
    """Applique tous les traitements et renvoie les résultats."""
    return {
        "transactions": flag_transactions(transactions),
        "sent_by_iban": sum_sent_by_iban(transactions),
        "sent_by_bank": sum_sent_by_bank(transactions),
        "received_by_iban": sum_received_by_iban(transactions),
    }