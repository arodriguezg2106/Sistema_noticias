"""Executive Weekly Summary Generator grouped by Federal Entity (State)."""

from __future__ import annotations

from collections import Counter
from typing import Any


STATE_CATEGORIES = {
    "GOV_EEUU": {
        "label": "Gobernatura en observación de EEUU",
        "class_name": "gov-eeuu",
        "description": "Estados destacados por la clasificación de observación de EEUU.",
        "states": {"Baja California", "Chihuahua", "Michoacán", "Quintana Roo", "Sinaloa", "Sonora"},
    },
    "RENOV_GOV": {
        "label": "Renovación de gubernatura 2027",
        "class_name": "renov-gov",
        "description": "Entidades que renovarán titular del Poder Ejecutivo local.",
        "states": {"Nuevo León", "Zacatecas", "Guerrero", "Campeche", "Tabasco", "San Luis Potosí", "Nayarit", "Baja California Sur", "Querétaro", "Morelos"},
    },
    "RENOV_CONGRESO": {
        "label": "Renovación de Congreso local",
        "class_name": "renov-congreso",
        "description": "Entidades que renovarán Congreso local sin cambio de gubernatura.",
        "states": {"Jalisco", "Coahuila", "Durango", "Tamaulipas", "Hidalgo", "Estado de México", "Ciudad de México", "Puebla", "Veracruz", "Oaxaca", "Chiapas", "Yucatán"},
    },
}


class WeeklyStateSummaryGenerator:
    """Consolidate weekly political activity for a single State into an executive summary."""

    def __init__(self, state_name: str, events: list[dict[str, Any]]) -> None:
        self.state_name = state_name
        self.events = events

    def _get_category(self) -> dict[str, str]:
        for code, info in STATE_CATEGORIES.items():
            if self.state_name in info["states"]:
                return {"code": code, "label": info["label"], "class_name": info["class_name"]}
        return {"code": "SIN_CAMBIOS", "label": "Sin cambios", "class_name": "sin-cambios"}

    def generate(self) -> dict[str, Any]:
        category = self._get_category()
        if not self.events:
            return {
                "state": self.state_name,
                "category": category,
                "event_count": 0,
                "max_importance": "Bajo",
                "total_score": 0,
                "parties": [],
                "actors": [],
                "event_types": [],
                "summary": f"Sin actividad electoral relevante registrada en {self.state_name} durante los últimos 7 días.",
            }

        event_types = Counter(str(event.get("event_type") or "Otro") for event in self.events)
        all_actors: set[str] = set()
        all_parties: set[str] = set()
        total_score = 0
        importance_levels = set()

        for event in self.events:
            total_score += int(event.get("priority_score", 0))
            importance_levels.add(str(event.get("importance_level", "Bajo")))
            for actor in event.get("actors", []):
                all_actors.add(str(actor))
            for pub in event.get("publications", []):
                party = pub.get("party_detected")
                if party:
                    all_parties.add(str(party))

        # Determine highest importance
        if "Crítico" in importance_levels:
            max_importance = "Crítico"
        elif "Alto" in importance_levels:
            max_importance = "Alto"
        elif "Medio" in importance_levels:
            max_importance = "Medio"
        else:
            max_importance = "Bajo"

        # Build narrative summary
        top_types = [t for t, _ in event_types.most_common(2)]
        types_str = " y ".join(top_types) if top_types else "eventos electorales"

        actors_list = sorted(all_actors)
        parties_list = sorted(all_parties)

        summary_parts = [
            f"Durante los últimos 7 días en {self.state_name}, la actividad política se concentró principalmente en {types_str.lower()} ({len(self.events)} evento{'s' if len(self.events) != 1 else ''} registrado{'s' if len(self.events) != 1 else ''})."
        ]

        if parties_list or actors_list:
            parts = []
            if parties_list:
                parts.append(f"los partidos {', '.join(parties_list)}")
            if actors_list:
                parts.append(f"los actores {', '.join(actors_list)}")
            summary_parts.append(f"Se identificó el involucramiento de {' e '.join(parts)}.")
        else:
            summary_parts.append("El monitoreo mantiene seguimiento de los acontecimientos institucionales en la entidad.")

        return {
            "state": self.state_name,
            "category": category,
            "event_count": len(self.events),
            "max_importance": max_importance,
            "total_score": total_score,
            "parties": parties_list,
            "actors": actors_list,
            "event_types": event_types.most_common(),
            "summary": " ".join(summary_parts),
        }
