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


def test_context_sentence_varies_by_event_type(configs) -> None:
    """Fase 1: context templates should differ across event types."""
    generator = SummaryGenerator(configs)
    pub_encuesta = make_publication(
        "Encuesta muestra ventaja del PAN en Nuevo León en 2027",
        "La encuesta reporta preferencias electorales en Nuevo León en 2027.",
        event_type="Nueva encuesta",
    )
    pub_registro = make_publication(
        "Candidato del PAN se registra en Nuevo León en 2027",
        "El PAN registró a su candidato para la gubernatura de Nuevo León en 2027.",
        event_type="Registro o anuncio de candidatura",
    )

    summary_encuesta = generator.generate(pub_encuesta, [])
    summary_registro = generator.generate(pub_registro, [])

    # The old generator would produce the same "El asunto electoral principal
    # corresponde a …" phrase for every event type. Now they should differ.
    assert "El asunto electoral principal corresponde" not in summary_encuesta
    assert "El asunto electoral principal corresponde" not in summary_registro
    assert "Nuevo León" in summary_encuesta
    assert "Nuevo León" in summary_registro
    assert 35 <= len(summary_encuesta.split()) <= 60
    assert 35 <= len(summary_registro.split()) <= 60


def test_fit_main_cuts_at_clause_boundary(configs) -> None:
    """Fase 2: truncation should prefer clause boundaries over mid-phrase cuts."""
    generator = SummaryGenerator(configs)
    # Build a publication with a very long body sentence that forces truncation.
    long_body = (
        "El candidato del PAN señaló que buscará fortalecer la coalición electoral "
        "en Nuevo León, donde los partidos aliados preparan su estrategia para "
        "el proceso de 2027 en cada municipio del estado."
    )
    publication = make_publication(
        "PAN prepara estrategia electoral en Nuevo León",
        long_body,
        event_type="Coalición o alianza",
    )

    summary = generator.generate(publication, [])

    # The summary should not end with a dangling preposition or article.
    main_sentence = summary.split(".")[0]
    last_word = main_sentence.strip().split()[-1].lower().rstrip(".,;:")
    dangling = {"de", "del", "a", "al", "con", "en", "por", "para", "que", "y",
                "la", "el", "lo", "las", "los", "un", "una"}
    assert last_word not in dangling, f"Main sentence ends with dangling word: '{last_word}'"
    assert 35 <= len(summary.split()) <= 60


def test_enforce_limits_avoids_generic_filler(configs) -> None:
    """Fase 3: short summaries should prefer body content over generic muletilla."""
    generator = SummaryGenerator(configs)
    summary = generator.generate(
        make_publication(
            "PAN anuncia candidato en Nuevo León en 2027",
            "El PAN registró a su candidato para la gubernatura de Nuevo León en 2027. "
            "La dirigencia estatal confirmó el registro ante el INE.",
        ),
        [],
    )

    # The old generic filler was "según la información electoral disponible en
    # la publicación"; it should no longer appear.
    assert "según la información electoral disponible en la publicación" not in summary
    assert 35 <= len(summary.split()) <= 60


def test_neutral_main_includes_state_and_actor(configs) -> None:
    """Fase 4: neutral fallback should mention state and actor when available."""
    generator = SummaryGenerator(configs)
    actor = Actor("María López", "political", party="PRI", state="Jalisco")
    # Every body sentence triggers a future consequence pattern, forcing the
    # neutral fallback path.
    publication = make_publication(
        "María López ganará la gubernatura de Jalisco",
        "María López ganará sin oposición. Arrasará en Jalisco.",
        state="Jalisco",
        party="PRI",
        event_type="Registro o anuncio de candidatura",
    )

    summary = generator.generate(publication, [actor])

    # The old fallback was "X aparece vinculado con …"; now it should be richer.
    assert "aparece vinculado" not in summary
    assert "María López" in summary
    assert "Jalisco" in summary
    assert 35 <= len(summary.split()) <= 60


def test_weekly_state_summary_generator() -> None:
    from app.summaries.weekly import WeeklyStateSummaryGenerator
    events = [
        {
            "state": "Zacatecas",
            "event_type": "Registro o anuncio de candidatura",
            "importance_level": "Alto",
            "priority_score": 12,
            "actors": ["Ulises Mejía Haro"],
            "publications": [{"party_detected": "Morena"}],
        },
        {
            "state": "Zacatecas",
            "event_type": "Nueva encuesta",
            "importance_level": "Medio",
            "priority_score": 8,
            "actors": ["Ulises Mejía Haro"],
            "publications": [{"party_detected": "PAN"}],
        },
    ]

    generator = WeeklyStateSummaryGenerator("Zacatecas", events)
    result = generator.generate()

    assert result["state"] == "Zacatecas"
    assert result["event_count"] == 2
    assert result["max_importance"] == "Alto"
    assert result["total_score"] == 20
    assert "Morena" in result["parties"]
    assert "Ulises Mejía Haro" in result["actors"]
    assert "Zacatecas" in result["summary"]


