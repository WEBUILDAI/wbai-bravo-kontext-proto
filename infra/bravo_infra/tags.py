"""Pflicht-Tags für alle Azure-Ressourcen des Prototyps."""

BASE_TAGS: dict[str, str] = {
    "environment": "nonprod",
    "stage": "prototype",
    "project": "bravo",
    "expires": "2027-02-24",
}


def make_tags(owner: str, **extra: str) -> dict[str, str]:
    """Baut die Pflicht-Tags inklusive ``owner``.

    Args:
        owner: E-Mail-Adresse der verantwortlichen Person (Pulumi-Config ``owner``).
        **extra: Zusätzliche Tags. Pflicht-Tags können nicht überschrieben werden.

    Returns:
        Neues Dict mit Pflicht-Tags und Zusatz-Tags.

    Raises:
        ValueError: Wenn ``owner`` leer ist oder keine E-Mail-Adresse ist.
    """
    if not owner or "@" not in owner:
        raise ValueError("Pulumi-Config 'owner' muss eine E-Mail-Adresse sein")
    return {**extra, **BASE_TAGS, "owner": owner}
