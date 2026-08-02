"""Command-line entry point for the SMEE prototype."""

from __future__ import annotations

import argparse
import logging
import sqlite3
from pathlib import Path

from app.collectors import (
    CollectorError,
    CompositeCollector,
    MockCollector,
    NewsSitemapCollector,
    RSSCollector,
)
from app.config import ConfigLoader, ConfigurationError
from app.exports import ExcelReportExporter
from app.pipeline import PipelineError, ProcessingPipeline
from app.reports import HtmlReportGenerator
from app.repositories import Database
from app.utils.logging import configure_logging


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="SMEE deterministic monitoring prototype")
    parser.add_argument(
        "--collector", choices=("mock", "rss", "live"), default="mock",
        help="Origen: muestra JSON, sólo RSS o todas las fuentes públicas reales",
    )
    parser.add_argument("--input", type=Path, default=root / "data" / "mock_publications.json")
    parser.add_argument("--database", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument(
        "--excel", type=Path, default=None,
        help="Ruta del libro Excel; se genera automáticamente junto con el HTML",
    )
    parser.add_argument("--config-dir", type=Path, default=root / "config")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parent
    database_path = args.database or root / "data" / (
        "smee-rss.db" if args.collector in {"rss", "live"} else "smee.db"
    )
    report_path = args.report or root / "data" / (
        "rss-report.html" if args.collector in {"rss", "live"} else "report.html"
    )
    excel_path = args.excel or root / "data" / (
        "reporte-electoral.xlsx"
        if args.collector in {"rss", "live"}
        else "reporte-demostracion.xlsx"
    )
    configure_logging(root / "logs", args.verbose)
    logger = logging.getLogger(__name__)
    try:
        configs = ConfigLoader(args.config_dir).load_all()
        database = Database(database_path)
        pipeline = ProcessingPipeline(database, configs)
        pipeline.initialize()
        if args.collector == "live":
            collector = CompositeCollector([
                RSSCollector(configs["rss_sources"]),
                NewsSitemapCollector(configs["news_sitemaps"]),
            ])
        elif args.collector == "rss":
            collector = RSSCollector(configs["rss_sources"])
        else:
            collector = MockCollector(args.input)
        summary = pipeline.run(collector)
        report = HtmlReportGenerator(
            pipeline.events,
            pipeline.publications,
            root / "app" / "reports" / "templates",
        ).generate(report_path, summary)
        excel = ExcelReportExporter(database).export(excel_path)
    except (ConfigurationError, CollectorError, PipelineError, sqlite3.Error, OSError, ValueError) as exc:
        logger.error("Execution failed: %s", exc)
        return 1
    logger.info(
        "Finished: %d collected, %d new events, %d updated, %d already stored, %d duplicates",
        summary.collected, summary.new_events, summary.updated_events,
        summary.already_seen, summary.duplicates,
    )
    print(f"Reporte generado: {report.resolve()}")
    print(f"Excel generado: {excel.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
