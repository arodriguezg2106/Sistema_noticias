from datetime import datetime, timezone

from app.collectors.base import Collector
from app.collectors import MockCollector
from app.models import CollectedPublication
from app.pipeline import ProcessingPipeline
from app.reports import HtmlReportGenerator
from app.repositories import Database


def test_end_to_end_pipeline_creates_events_audit_and_report(tmp_path, project_root, configs) -> None:
    database = Database(tmp_path / "smee.db")
    pipeline = ProcessingPipeline(database, configs)
    pipeline.initialize()

    summary = pipeline.run(MockCollector(project_root / "data" / "mock_publications.json"))
    output = HtmlReportGenerator(
        pipeline.events,
        pipeline.publications,
        project_root / "app" / "reports" / "templates",
    ).generate(tmp_path / "report.html", summary)

    assert summary.collected == 6
    assert summary.inserted == 6
    assert summary.duplicates == 1
    assert summary.new_events == 4
    assert summary.updated_events == 1
    events = pipeline.events.list_report_data()
    assert len(events) == 4
    survey = next(event for event in events if event["event_type"] == "Nueva encuesta")
    resolution = next(event for event in events if event["event_type"] == "Resolución electoral")
    assert survey["priority_score"] == 7
    assert any("duplicada" in reason for reason in survey["score_reasons"])
    assert any(item["relationship_type"] == "duplicate" for item in survey["publications"])
    assert resolution["priority_score"] == 14
    assert all(35 <= len(event["description"].split()) <= 60 for event in events)
    assert pipeline.rule_matches.for_publication(1)
    html = output.read_text(encoding="utf-8")
    assert "Reporte ejecutivo" in html
    assert "Nueva encuesta" in html
    assert "Revisión manual" in html
    assert "Datos de demostración" in html
    assert "fuente simulada; sin enlace externo" in html
    assert 'href="https://horizonte.example' not in html
    assert 'href="https://www.te.gob.mx/sentencias/te-2026-771"' not in html

    second_run = pipeline.run(MockCollector(project_root / "data" / "mock_publications.json"))
    assert second_run.already_seen == 6
    assert second_run.inserted == 0
    assert pipeline.publications.count() == 6

    class LocalCollector(Collector):
        def collect(self) -> list[CollectedPublication]:
            return [
                CollectedPublication(
                    source_name="Noticias de Occidente",
                    external_id="local-without-state",
                    title="Nueva encuesta de intención de voto rumbo a la gubernatura",
                    url="https://occidente.example/politica/encuesta-sin-entidad",
                    published_at=datetime(2026, 7, 31, 12, tzinfo=timezone.utc),
                    raw_text="El sondeo electoral presenta nuevas preferencias.",
                )
            ]

    local_summary = pipeline.run(LocalCollector())
    assert local_summary.new_events == 1
    with database.connect() as connection:
        row = connection.execute(
            "SELECT state_detected FROM publications WHERE external_id='local-without-state'"
        ).fetchone()
    assert row["state_detected"] == "Jalisco"


def test_central_settings_override(tmp_path, configs) -> None:
    """Verify that settings.yaml parameters correctly configure components."""
    custom_configs = dict(configs)
    custom_configs["settings"] = {
        "periodo_y_recoleccion": {
            "antiguedad_maxima_horas": 72,
            "limite_articulos_por_rss": 25,
            "ventana_agrupacion_dias": 5,
            "ano_electoral_defecto": "2030",
        },
        "resumenes": {
            "palabras_minimas": 40,
            "palabras_maximas": 70,
        },
    }
    database = Database(tmp_path / "smee_settings.db")
    pipeline = ProcessingPipeline(database, custom_configs)

    assert pipeline.grouper.settings["temporal_window_days"] == 5
    assert pipeline.summaries.minimum_words == 40
    assert pipeline.summaries.maximum_words == 70
    assert pipeline.summaries.default_electoral_year == "2030"

