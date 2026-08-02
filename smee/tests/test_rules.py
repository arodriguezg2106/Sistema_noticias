from datetime import datetime, timezone

from app.models import Publication
from app.normalizers.text import content_hash, normalize_text, normalize_url
from app.rules import RuleEngine


def test_rule_engine_detects_state_party_actor_and_event(configs) -> None:
    title = "Encuesta da ventaja a María López en Chihuahua"
    body = "La intención de voto favorece a María López, del PAN, en Chihuahua."
    now = datetime.now(timezone.utc)
    publication = Publication(
        id=1,
        source_id=1,
        title=title,
        url="https://example.mx/a",
        normalized_url=normalize_url("https://example.mx/a"),
        published_at=now,
        collected_at=now,
        author=None,
        raw_text=body,
        normalized_text=normalize_text(f"{title} {body}"),
        content_hash=content_hash(title, body),
    )

    result = RuleEngine(configs).classify(publication)

    assert result.state == "Chihuahua"
    assert result.party == "PAN"
    assert result.actor_names == ["María López"]
    assert result.event_type == "Nueva encuesta"
    assert any(match.rule_type == "event_type" for match in result.matches)


def test_multiple_states_require_review(configs) -> None:
    now = datetime.now(timezone.utc)
    publication = Publication(
        id=2, source_id=1, title="Elecciones en Chihuahua y Jalisco",
        url="https://example.mx/b", normalized_url="https://example.mx/b",
        published_at=now, collected_at=now, author=None,
        raw_text="Elecciones de gubernatura en Chihuahua y Jalisco.",
        normalized_text="elecciones", content_hash="hash",
    )
    result = RuleEngine(configs).classify(publication)
    assert result.needs_review
    assert any("entidades" in reason for reason in result.review_reasons)


def test_federal_election_is_classified_as_national_scope(configs) -> None:
    now = datetime.now(timezone.utc)
    publication = Publication(
        id=3, source_id=1,
        title="INE aprueba plan integral y calendario del Proceso Electoral Federal 2026-2027",
        url="https://example.mx/c", normalized_url="https://example.mx/c",
        published_at=now, collected_at=now, author=None, raw_text="",
        normalized_text="proceso electoral federal", content_hash="hash-c",
    )
    result = RuleEngine(configs).classify(publication)
    assert result.state == "Nacional"
    assert result.event_type == "Publicación oficial de calendario electoral"
    assert result.actor_names == ["Instituto Nacional Electoral"]


def test_candidate_registration_in_nuevo_leon(configs) -> None:
    now = datetime.now(timezone.utc)
    publication = Publication(
        id=4, source_id=1,
        title="Aldo Fasci se registra al PAN como candidato a gobernar Nuevo León",
        url="https://example.mx/d", normalized_url="https://example.mx/d",
        published_at=now, collected_at=now, author=None,
        raw_text="Aldo Fasci, PAN, Nuevo León, Elecciones",
        normalized_text="aldo fasci pan nuevo leon", content_hash="hash-d",
    )
    result = RuleEngine(configs).classify(publication)
    assert result.state == "Nuevo León"
    assert result.party == "PAN"
    assert result.event_type == "Registro o anuncio de candidatura"
    assert result.actor_names == ["Aldo Fasci"]


def test_fasci_enrollment_variant_is_candidate_event(configs) -> None:
    now = datetime.now(timezone.utc)
    publication = Publication(
        id=5, source_id=1,
        title="Fasci no logra inscribirse como candidato del PAN",
        url="https://example.mx/nuevo-leon/fasci", normalized_url="https://example.mx/nuevo-leon/fasci",
        published_at=now, collected_at=now, author=None, raw_text="",
        normalized_text="fasci candidato pan", content_hash="hash-e",
    )
    result = RuleEngine(configs).classify(publication)
    assert result.state == "Nuevo León"
    assert result.event_type == "Registro o anuncio de candidatura"
    assert result.actor_names == ["Aldo Fasci"]
