"""Generate the local executive HTML report."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.models import ProcessingSummary
from app.repositories.events import EventRepository
from app.repositories.publications import PublicationRepository


class HtmlReportGenerator:
    def __init__(
        self,
        event_repository: EventRepository,
        publication_repository: PublicationRepository,
        template_dir: Path,
    ) -> None:
        self.event_repository = event_repository
        self.publication_repository = publication_repository
        self.environment = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def generate(self, output_path: Path, summary: ProcessingSummary) -> Path:
        events = self.event_repository.list_report_data()
        states = Counter(str(event["state"] or "Sin entidad") for event in events)
        grouped: dict[str, list[dict[str, object]]] = {}
        for event in events:
            grouped.setdefault(str(event["state"] or "Sin entidad"), []).append(event)
        review_items = self.publication_repository.list_review_items()
        has_mock_data = any(
            bool(publication["is_mock"])
            for event in events
            for publication in event["publications"]
        ) or any(bool(item["is_mock"]) for item in review_items)
        template = self.environment.get_template("report.html.j2")
        html = template.render(
            generated_at=datetime.now().astimezone(),
            summary=summary,
            state_activity=states.most_common(),
            high_priority=[event for event in events if event["importance_level"] in {"Crítico", "Alto"}],
            events_by_state=sorted(grouped.items()),
            review_items=review_items,
            has_mock_data=has_mock_data,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        return output_path
