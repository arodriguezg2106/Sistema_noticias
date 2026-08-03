"""Generate the local executive HTML report."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.models import ProcessingSummary
from app.repositories.events import EventRepository
from app.repositories.publications import PublicationRepository
from app.summaries.weekly import WeeklyStateSummaryGenerator


CANONICAL_STATES = {
    "aguascalientes": "Aguascalientes",
    "baja california": "Baja California",
    "baja california sur": "Baja California Sur",
    "baja sur": "Baja California Sur",
    "b.c.s.": "Baja California Sur",
    "bcs": "Baja California Sur",
    "campeche": "Campeche",
    "chiapas": "Chiapas",
    "chihuahua": "Chihuahua",
    "ciudad de mexico": "Ciudad de México",
    "cdmx": "Ciudad de México",
    "coahuila": "Coahuila",
    "colima": "Colima",
    "durango": "Durango",
    "estado de mexico": "Estado de México",
    "edomex": "Estado de México",
    "guanajuato": "Guanajuato",
    "guerrero": "Guerrero",
    "hidalgo": "Hidalgo",
    "jalisco": "Jalisco",
    "michoacan": "Michoacán",
    "michoacán": "Michoacán",
    "morelos": "Morelos",
    "nayarit": "Nayarit",
    "nuevo leon": "Nuevo León",
    "nuevo león": "Nuevo León",
    "oaxaca": "Oaxaca",
    "puebla": "Puebla",
    "queretaro": "Querétaro",
    "querétaro": "Querétaro",
    "quintana roo": "Quintana Roo",
    "san luis potosi": "San Luis Potosí",
    "san luis potosí": "San Luis Potosí",
    "sinaloa": "Sinaloa",
    "sonora": "Sonora",
    "tabasco": "Tabasco",
    "tamaulipas": "Tamaulipas",
    "tlaxcala": "Tlaxcala",
    "veracruz": "Veracruz",
    "yucatan": "Yucatán",
    "yucatán": "Yucatán",
    "zacatecas": "Zacatecas",
    "zac": "Zacatecas",
    "nacional": "Nacional",
}


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
        
        # Load all state matches per publication from database
        pub_states: dict[int, set[str]] = {}
        try:
            with self.event_repository.database.connect() as conn:
                rows = conn.execute(
                    "SELECT publication_id, matched_value FROM rule_matches WHERE rule_type='state'"
                ).fetchall()
                for row in rows:
                    raw_val = str(row["matched_value"]).lower().strip()
                    canonical = CANONICAL_STATES.get(raw_val, str(row["matched_value"]))
                    pub_states.setdefault(int(row["publication_id"]), set()).add(canonical)
        except Exception:
            pass

        grouped: dict[str, list[dict[str, object]]] = {}
        for event in events:
            event_states: set[str] = set()
            if event.get("state"):
                raw_st = str(event["state"]).lower().strip()
                event_states.add(CANONICAL_STATES.get(raw_st, str(event["state"])))
            
            for pub in event.get("publications", []):
                pid = pub.get("id") or pub.get("publication_id")
                if pid and int(pid) in pub_states:
                    event_states.update(pub_states[int(pid)])

            if not event_states:
                event_states.add("Sin entidad")

            for st_name in event_states:
                grouped.setdefault(st_name, []).append(event)
        
        states = Counter()
        for st, evts in grouped.items():
            states[st] = len(evts)

        # Calculate consolidated weekly state summaries
        weekly_state_summaries = []
        for state_name, state_events in sorted(grouped.items()):
            generator = WeeklyStateSummaryGenerator(state_name, state_events)
            weekly_state_summaries.append(generator.generate())

        # Top 5 most relevant events by score
        top_5_events = sorted(events, key=lambda e: int(e.get("priority_score", 0)), reverse=True)[:5]

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
            top_5_events=top_5_events,
            events_by_state=sorted(grouped.items()),
            weekly_state_summaries=weekly_state_summaries,
            review_items=review_items,
            has_mock_data=has_mock_data,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        return output_path
