"""Generate manual Boolean audit queries for state coverage."""

from __future__ import annotations

from datetime import date, timedelta


def boolean_audit_query(state: str, aliases: list[str], today: date | None = None) -> str:
    today = today or date.today()
    after = today - timedelta(days=7)
    locations = " OR ".join(f'"{item}"' for item in [state, *aliases[:2]])
    return (
        '("gubernatura" OR "elecciones 2027" OR "precandidatura" OR '
        f'"intención de voto") ({locations}) after:{after.isoformat()} '
        "-fútbol -deportes"
    )

