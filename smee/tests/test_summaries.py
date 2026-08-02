from datetime import datetime, timezone

from app.models import Actor, Publication
from app.normalizers.text import normalize_text
from app.summaries import SummaryGenerator


def make_publication(
    title: str,
    body: str,
    *,
    state: str = "Nuevo León",
    party: str = "PAN",
    event_type: str = "Registro o anuncio de candidatura",
) -> Publication:
    now = datetime(2026, 7, 31, tzinfo=timezone.utc)
    return Publication(
        source_id=1,
        title=title,
        url="https://example.com/noticia",
        normalized_url="https://example.com/noticia",
        published_at=now,
        collected_at=now,
        author="Redacción",
        raw_text=body,
        normalized_text=normalize_text(f"{title} {body}"),
        content_hash="summary-test",
        state_detected=state,
        party_detected=party,
        event_type_detected=event_type,
    )


def test_uses_prudent_body_verb_and_excludes_opinion(configs) -> None:
    generator = SummaryGenerator(configs)
    actor = Actor("Aldo Fasci", "political", party="PAN", state="Nuevo León")
    publication = make_publication(
        "Aldo Fasci asegura que ganará la gubernatura de Nuevo León",
        "Aldo Fasci señaló que buscará registrarse como candidato del PAN a la "
        "gubernatura de Nuevo León en 2027. En opinión del autor, ganará con facilidad.",
    )

    summary = generator.generate(publication, [actor])

    assert "señaló" in summary
    assert "asegura" not in summary
    assert "opinión del autor" not in summary
    assert "ganará con facilidad" not in summary
    assert "Nuevo León" in summary
    assert "PAN" in summary
    assert "2027" in summary
    assert 35 <= len(summary.split()) <= 60
    assert summary.count(".") == 2


def test_lists_all_parties_found_in_evidence(configs) -> None:
    generator = SummaryGenerator(configs)
    publication = make_publication(
        "Encuesta mide la gubernatura de Nuevo León en 2027",
        "La encuesta reporta preferencias para PAN, Morena y Movimiento Ciudadano "
        "en la elección de Nuevo León de 2027.",
        event_type="Nueva encuesta",
    )

    summary = generator.generate(publication, [])

    assert all(party in summary for party in ("PAN", "Morena", "Movimiento Ciudadano"))
    assert 35 <= len(summary.split()) <= 60


def test_does_not_present_future_consequence_as_fact(configs) -> None:
    generator = SummaryGenerator(configs)
    actor = Actor("Aldo Fasci", "political", party="PAN", state="Nuevo León")
    publication = make_publication(
        "Aldo Fasci ganará y reconfigurará la elección de Nuevo León",
        "El PAN informó sobre el registro de Aldo Fasci para la gubernatura de Nuevo León en 2027.",
    )

    summary = generator.generate(publication, [actor])

    assert "ganará" not in summary
    assert "reconfigurará" not in summary
    assert "informó" in summary
    assert 35 <= len(summary.split()) <= 60
