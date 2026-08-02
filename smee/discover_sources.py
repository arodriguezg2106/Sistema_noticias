"""CLI for respectful source endpoint discovery and coverage mapping."""

from __future__ import annotations

import argparse
import logging
from datetime import datetime
from pathlib import Path

import yaml

from app.collectors import CollectorError
from app.config import ConfigLoader, ConfigurationError
from app.source_discovery import SourceCoverageReport, SourceDiscovery, SourceSeed
from app.utils.logging import configure_logging


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Discover public RSS/Atom/sitemap endpoints")
    parser.add_argument("--state", help="Inspeccionar sólo fuentes asignadas a esta entidad")
    parser.add_argument("--include-national", action="store_true")
    parser.add_argument("--limit", type=int, default=10, help="Máximo de dominios; 0 procesa todos")
    parser.add_argument("--offset", type=int, default=0, help="Posición inicial para ejecución por lotes")
    parser.add_argument("--config-dir", type=Path, default=root / "config")
    parser.add_argument("--output", type=Path, default=root / "data" / "source-discovery.yaml")
    parser.add_argument("--report", type=Path, default=root / "data" / "source-coverage.html")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parent
    configure_logging(root / "logs", args.verbose)
    logger = logging.getLogger(__name__)
    try:
        if args.limit < 0 or args.offset < 0:
            raise ValueError("--limit and --offset cannot be negative")
        loader = ConfigLoader(args.config_dir)
        registry = loader.load("source_registry.yaml")
        states_config = loader.load("states.yaml")
        seeds = [SourceSeed.from_mapping(item) for item in registry.get("sources", [])]
        seeds = [seed for seed in seeds if seed.enabled]
        selected = seeds
        if args.state:
            selected = [seed for seed in seeds if args.state in seed.states]
            if args.include_national:
                selected.extend(seed for seed in seeds if not seed.states and seed not in selected)
        selected = selected[args.offset :]
        if args.limit:
            selected = selected[: args.limit]
        results = SourceDiscovery(registry.get("settings", {})).discover_many(selected)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            yaml.safe_dump(
                {
                    "generated_at": datetime.now().astimezone().isoformat(),
                    "registry_sources": len(seeds),
                    "inspected_sources": len(results),
                    "results": [result.as_dict() for result in results],
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        report = SourceCoverageReport(root / "app" / "reports" / "templates").generate(
            args.report, states_config, seeds, results
        )
    except (ConfigurationError, CollectorError, OSError, ValueError, KeyError) as exc:
        logger.error("Source discovery failed: %s", exc)
        return 1
    print(f"Fuentes inspeccionadas: {len(results)}")
    print(f"Resultados: {args.output.resolve()}")
    print(f"Cobertura: {report.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

