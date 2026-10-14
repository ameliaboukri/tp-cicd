"""Mécanisme de retry générique (réutilisé au niveau 2 pour le S3)."""
import time


class RetryError(Exception):
    """Levée quand toutes les tentatives ont échoué."""


def retry(func, *, max_attempts=3, delay=1.0, backoff=2.0,
          retry_on=(Exception,), label="opération", sleep=time.sleep):
    """Appelle func() jusqu'à ce qu'elle réussisse ou que max_attempts soit atteint.

    - delay   : attente avant la 2e tentative (en secondes)
    - backoff : multiplicateur du délai à chaque échec (1s, 2s, 4s...)
    - retry_on: types d'erreurs considérées comme temporaires
    """
    if max_attempts < 1:
        raise ValueError("max_attempts doit être >= 1")

    wait = delay
    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except retry_on as e:
            print(f"  [ERREUR] {label} - tentative {attempt}/{max_attempts} échouée : "
                  f"{type(e).__name__}: {e}", flush=True)
            if attempt == max_attempts:
                raise RetryError(
                    f"{label} : abandon après {max_attempts} tentatives "
                    f"(dernière erreur : {e})"
                ) from e
            print(f"  [RETRY]  nouvelle tentative dans {wait:.1f} s...", flush=True)
            sleep(wait)
            wait *= backoff