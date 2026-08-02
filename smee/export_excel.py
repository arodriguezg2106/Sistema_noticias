"""Export an existing SMEE SQLite database without collecting new publications."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from app.exports import ExcelReportExporter
from app.repositories import Database


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Exportar la base SMEE a Excel")
    parser.add_argument("--database", type=Path, default=root / "data" / "smee-rss.db")
    parser.add_argument("--output", type=Path, default=root / "data" / "reporte-electoral.xlsx")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.database.is_file():
        print(f"No existe la base de datos: {args.database.resolve()}")
        return 1
    try:
        output = ExcelReportExporter(Database(args.database)).export(args.output)
    except (sqlite3.Error, OSError, ValueError) as exc:
        print(f"No se pudo generar el Excel: {exc}")
        return 1
    print(f"Excel generado: {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
