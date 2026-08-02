from datetime import datetime, timezone

from app.models import Publication, Source
from app.repositories import Database, PublicationRepository, SourceRepository


def publication(source_id: int, url: str, digest: str) -> Publication:
    now = datetime.now(timezone.utc)
    return Publication(
        source_id=source_id,
        title="Título",
        url=url,
        normalized_url=url,
        published_at=now,
        collected_at=now,
        author=None,
        raw_text="Texto",
        normalized_text="titulo texto",
        content_hash=digest,
    )


def test_exact_duplicates_are_detected_by_url_and_hash(tmp_path) -> None:
    database = Database(tmp_path / "test.db")
    database.initialize()
    source = SourceRepository(database).upsert(Source("Fuente", "media", "https://example.mx"))
    repository = PublicationRepository(database)
    repository.add(publication(source.id or 0, "https://example.mx/a", "hash-a"))

    by_url = repository.find_exact_duplicate("https://example.mx/a", "other-hash")
    by_hash = repository.find_exact_duplicate("https://example.mx/other", "hash-a")

    assert by_url.is_duplicate and by_url.reason == "exact_url"
    assert by_hash.is_duplicate and by_hash.reason == "exact_content_hash"

