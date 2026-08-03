"""Configurable, explainable classification engine."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.models import ClassificationResult, Publication, RuleMatch
from app.normalizers.text import normalize_text


def _literal_occurrences(text: str, literal: str) -> int:
    normalized = normalize_text(literal)
    if not normalized:
        return 0
    return len(re.findall(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", text))


class RuleEngine:
    """Evaluate catalog terms and regex rules while preserving every match."""

    def __init__(self, configs: dict[str, dict[str, Any]]) -> None:
        self.states = configs["states"].get("states", [])
        self.national_scope = configs["states"].get("national_scope", {})
        self.parties = configs["parties"].get("parties", [])
        self.actors = configs["actors"].get("actors", [])
        self.event_types = configs["event_types"].get("event_types", [])
        self.settings = configs["event_types"].get("detection", {})

    def classify(self, publication: Publication) -> ClassificationResult:
        if publication.id is None:
            raise ValueError("Publication must be persisted before classification")
        text = normalize_text(f"{publication.title} {publication.raw_text} {publication.url}")
        matches: list[RuleMatch] = []
        review_reasons: list[str] = []

        state, state_ambiguous = self._detect_catalog(
            text, self.states, "state", publication.id, matches
        )
        if state is None:
            national_name = str(self.national_scope.get("name", "Nacional"))
            for alias in self.national_scope.get("aliases", []):
                if _literal_occurrences(text, str(alias)):
                    state = national_name
                    matches.append(
                        RuleMatch(
                            publication.id,
                            f"detect_scope:{national_name}",
                            "scope",
                            str(alias),
                            1,
                        )
                    )
                    break
        if state_ambiguous:
            review_reasons.append("Se detectaron varias entidades con fuerza similar")
        municipality = self._detect_municipality(text, state)
        party, party_ambiguous = self._detect_catalog(
            text, self.parties, "party", publication.id, matches
        )
        if party_ambiguous:
            review_reasons.append("Se detectaron varios partidos con fuerza similar")
        actor_names = self._detect_actors(text, publication.id, matches)
        event_type, event_ambiguous = self._detect_event_type(text, publication.id, matches, party, actor_names)
        if event_ambiguous:
            review_reasons.append("Varios tipos de evento obtuvieron puntuaciones equivalentes")
        if event_type is None:
            review_reasons.append("No se alcanzó el umbral para clasificar el tipo de evento")
        if state is None:
            review_reasons.append("No se detectó una entidad federativa")
        return ClassificationResult(
            state=state,
            municipality=municipality,
            party=party,
            event_type=event_type,
            actor_names=actor_names,
            matches=matches,
            needs_review=bool(review_reasons),
            review_reasons=review_reasons,
        )

    def _detect_catalog(
        self,
        text: str,
        entries: list[dict[str, Any]],
        rule_type: str,
        publication_id: int,
        matches: list[RuleMatch],
    ) -> tuple[str | None, bool]:
        scores: dict[str, int] = defaultdict(int)
        for entry in entries:
            name = str(entry["name"])
            for alias in [name, *entry.get("aliases", [])]:
                count = _literal_occurrences(text, str(alias))
                if count:
                    scores[name] += count
                    matches.append(
                        RuleMatch(publication_id, f"detect_{rule_type}:{name}", rule_type, str(alias), count)
                    )
        if not scores:
            return None, False
        ranking = sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))
        ambiguous = len(ranking) > 1 and ranking[0][1] - ranking[1][1] < int(
            self.settings.get("catalog_clear_margin", 2)
        )
        return ranking[0][0], ambiguous

    def _detect_municipality(self, text: str, state_name: str | None) -> str | None:
        if state_name is None:
            return None
        state_entry = next((item for item in self.states if item["name"] == state_name), None)
        if not state_entry:
            return None
        for municipality in state_entry.get("municipalities", []):
            if _literal_occurrences(text, str(municipality)):
                return str(municipality)
        return None

    def _detect_actors(
        self, text: str, publication_id: int, matches: list[RuleMatch]
    ) -> list[str]:
        detected: list[str] = []
        for actor in self.actors:
            name = str(actor["name"])
            for alias in [name, *actor.get("aliases", [])]:
                if _literal_occurrences(text, str(alias)):
                    detected.append(name)
                    matches.append(RuleMatch(
                        publication_id, f"detect_actor:{name}", "actor", str(alias), 0
                    ))
                    break
        return sorted(set(detected))

    def _has_electoral_anchor(
        self, text: str, party: str | None, actor_names: list[str]
    ) -> bool:
        if party is not None or bool(actor_names):
            return True
        electoral_keywords = {
            "gubernatura",
            "elección",
            "elecciones",
            "precampaña",
            "candidato",
            "candidata",
            "candidatos",
            "candidatas",
            "proceso electoral",
            "tepjf",
            "ine",
            "ople",
            "voto",
            "votación",
            "alianza electoral",
            "coalición",
            "propaganda",
            "encuesta estatal",
            "encuesta electoral",
            "encuesta interna",
            "intención de voto",
            "preferencia electoral",
        }
        for kw in electoral_keywords:
            if _literal_occurrences(text, kw):
                return True
        return False

    def _detect_event_type(
        self,
        text: str,
        publication_id: int,
        matches: list[RuleMatch],
        party: str | None = None,
        actor_names: list[str] | None = None,
    ) -> tuple[str | None, bool]:
        scores: dict[str, int] = defaultdict(int)
        for event_type in self.event_types:
            name = str(event_type["name"])
            for rule in event_type.get("positive", []):
                if self._matches_rule(text, rule):
                    weight = int(rule.get("weight", 1))
                    scores[name] += weight
                    matches.append(RuleMatch(
                        publication_id, f"event_positive:{name}", "event_type",
                        str(rule["pattern"]), weight,
                    ))
            for rule in event_type.get("negative", []):
                if self._matches_rule(text, rule):
                    weight = -abs(int(rule.get("weight", 1)))
                    scores[name] += weight
                    matches.append(RuleMatch(
                        publication_id, f"event_negative:{name}", "negative",
                        str(rule["pattern"]), weight,
                    ))
        if not scores:
            return None, False

        # Verify electoral anchor to filter out non-electoral false positives
        has_anchor = self._has_electoral_anchor(text, party, actor_names or [])
        if not has_anchor:
            # Require minimum_event_score >= 3 if no explicit electoral anchor is present
            for name in list(scores.keys()):
                scores[name] -= 1

        ranking = sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))
        minimum = int(self.settings.get("minimum_event_score", 2))
        if ranking[0][1] < minimum:
            return None, False
        ambiguity_margin = int(self.settings.get("event_ambiguity_margin", 1))
        ambiguous = len(ranking) > 1 and ranking[0][1] - ranking[1][1] <= ambiguity_margin
        return ranking[0][0], ambiguous

    @staticmethod
    def _matches_rule(text: str, rule: dict[str, Any]) -> bool:
        pattern = str(rule["pattern"])
        if rule.get("regex", False):
            try:
                return re.search(pattern, text, flags=re.IGNORECASE) is not None
            except re.error as exc:
                raise ValueError(f"Invalid configured regular expression {pattern!r}: {exc}") from exc
        return _literal_occurrences(text, pattern) > 0
