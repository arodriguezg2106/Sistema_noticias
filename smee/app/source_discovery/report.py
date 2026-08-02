"""Render source coverage and manual query reports."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.source_discovery.models import DiscoveryResult, SourceSeed
from app.source_discovery.queries import boolean_audit_query


class SourceCoverageReport:
    def __init__(self, template_dir: Path) -> None:
        self.environment = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def generate(
        self,
        output_path: Path,
        states_config: dict[str, Any],
        seeds: list[SourceSeed],
        results: list[DiscoveryResult],
    ) -> Path:
        result_by_url = {result.base_url: result for result in results}
        sources_by_state: dict[str, list[SourceSeed]] = defaultdict(list)
        for seed in seeds:
            for state in seed.states:
                sources_by_state[state].append(seed)
        coverage: list[dict[str, Any]] = []
        for state in states_config.get("states", []):
            name = str(state["name"])
            mapped = sources_by_state.get(name, [])
            verified = sum(
                1
                for seed in mapped
                if result_by_url.get(seed.base_url)
                and result_by_url[seed.base_url].status == "active"
            )
            coverage.append(
                {
                    "state": name,
                    "mapped": len(mapped),
                    "verified": verified,
                    "gap": len(mapped) < 3,
                    "query": boolean_audit_query(name, list(state.get("aliases", []))),
                }
            )
        template = self.environment.get_template("source_coverage.html.j2")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            template.render(
                generated_at=datetime.now().astimezone(),
                seeds=seeds,
                results=results,
                coverage=coverage,
                active_count=sum(result.status == "active" for result in results),
            ),
            encoding="utf-8",
        )
        return output_path

