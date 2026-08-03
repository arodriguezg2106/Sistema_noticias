"""Build concise electoral summaries without adding unsupported conclusions."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any

from app.models import Actor, Publication
from app.normalizers.text import normalize_text


@dataclass(frozen=True, slots=True)
class DetectedVerb:
    form: str
    strength: int
    position: int


class SummaryGenerator:
    """Generate a two-sentence, 35-to-60-word evidence-bound summary."""

    def __init__(self, configs: dict[str, dict[str, Any]]) -> None:
        self.rules = configs["summary_rules"]
        limits = self.rules.get("limits", {})
        central = configs.get("settings", {})
        resumenes = central.get("resumenes", {}) if isinstance(central.get("resumenes"), dict) else {}
        periodo = central.get("periodo_y_recoleccion", {}) if isinstance(central.get("periodo_y_recoleccion"), dict) else {}

        self.minimum_words = int(resumenes.get("palabras_minimas", limits.get("minimum_words", 35)))
        self.maximum_words = int(resumenes.get("palabras_maximas", limits.get("maximum_words", 60)))
        self.default_electoral_year = str(periodo.get("ano_electoral_defecto", self.rules.get("default_electoral_year", "2027")))
        self.party_catalog = configs.get("parties", {}).get("parties", [])
        self.context_templates: dict[str, list[str]] = self.rules.get("context_templates", {})
        self.verb_forms: list[tuple[str, int]] = []
        for item in self.rules.get("verbs", []):
            strength = int(item.get("strength", 1))
            for form in item.get("forms", []):
                self.verb_forms.append((str(form), strength))

    def generate(self, publication: Publication, actors: list[Actor]) -> str:
        """Return a summary grounded exclusively in the classified publication."""
        title = self._clean(publication.title)
        body_sentences = [
            sentence
            for sentence in self._sentences(publication.raw_text)
            if not self._excluded(sentence)
        ]
        actor_names = [actor.name for actor in actors]
        body_sentence = self._main_body_sentence(body_sentences, actor_names, publication)

        title_verb = self._verb(title)
        body_verb = self._verb(body_sentence) if body_sentence else None
        if body_sentence and (
            title_verb is None
            or body_verb is not None
            or self._contains_actor(body_sentence, actor_names)
        ):
            main = body_sentence
        else:
            main = title

        # A more forceful headline never overrides the wording used in the body.
        if title_verb and body_verb and title_verb.strength > body_verb.strength:
            main = body_sentence

        if self._future_consequence_as_fact(main):
            safer = next(
                (sentence for sentence in body_sentences if not self._future_consequence_as_fact(sentence)),
                "",
            )
            main = safer or self._neutral_main(publication, actor_names)

        main = self._ensure_actor(main, title, actor_names)
        context = self._context_sentence(publication, actors)
        main = self._fit_main(main, context)
        summary = f"{self._as_sentence(main)} {context}".strip()
        # Collect backup sentences for filler when the summary is too short.
        backup = [s for s in body_sentences if s != main and s != body_sentence]
        return self._enforce_limits(summary, backup)

    def _main_body_sentence(
        self,
        sentences: list[str],
        actor_names: list[str],
        publication: Publication,
    ) -> str:
        if not sentences:
            return ""
        electoral_terms = (
            "eleccion", "electoral", "candidat", "gubernatura", "encuesta",
            "partido", "coalicion", "alianza", "registro", "tribunal", "ine",
        )

        def score(sentence: str) -> tuple[int, int]:
            normalized = normalize_text(sentence)
            points = 0
            if self._contains_actor(sentence, actor_names):
                points += 6
            if self._verb(sentence):
                points += 4
            points += sum(1 for term in electoral_terms if term in normalized)
            for value in (publication.state_detected, publication.party_detected):
                if value and normalize_text(value) in normalized:
                    points += 2
            return points, -sentences.index(sentence)

        ranked = sorted(sentences, key=score, reverse=True)
        best = ranked[0]
        return best if score(best)[0] >= 4 else ""

    def _context_sentence(self, publication: Publication, actors: list[Actor]) -> str:
        state = publication.state_detected or self._actor_value(actors, "state")
        state_text = state or "una entidad no identificada en la publicación"
        parties = self._parties(publication, actors)
        party_text = self._join_spanish(parties) if parties else "ningún partido identificado"
        year = self._electoral_year(f"{publication.title} {publication.raw_text}")
        event_phrase = self.rules.get("event_phrases", {}).get(
            publication.event_type_detected,
            "un hecho relacionado con el proceso electoral",
        )
        # Select a template deterministically from YAML context_templates.
        event_type = publication.event_type_detected or ""
        templates = self.context_templates.get(
            event_type, self.context_templates.get("_default", [])
        )
        if templates:
            index = hash(publication.content_hash) % len(templates)
            template = str(templates[index])
            return template.format(
                event_phrase=event_phrase,
                state=state_text,
                parties=party_text,
                year=year,
            )
        # Fallback if no templates configured at all.
        return (
            f"El hecho se ubica en el contexto de {event_phrase} en {state_text}, "
            f"con mención de {party_text}, en el proceso electoral de {year}."
        )

    def _parties(self, publication: Publication, actors: list[Actor]) -> list[str]:
        text = f"{publication.title} {publication.raw_text}"
        found: list[str] = []
        for item in self.party_catalog:
            name = str(item.get("name", "")).strip()
            terms = [name, *[str(alias) for alias in item.get("aliases", [])]]
            if name and any(self._contains_term(text, term) for term in terms):
                found.append(name)
        if publication.party_detected and publication.party_detected not in found:
            found.append(publication.party_detected)
        for actor in actors:
            if actor.party and actor.party not in found and self._contains_term(text, actor.name):
                found.append(actor.party)
        return found

    def _electoral_year(self, text: str) -> str:
        matches = re.findall(r"\b(20\d{2})(?:\s*[-–‑/]\s*(20\d{2}))?\b", text)
        if matches:
            first, second = matches[0]
            return f"{first}-{second}" if second else first
        return str(getattr(self, "default_electoral_year", self.rules.get("default_electoral_year", "año no identificado")))

    def _verb(self, text: str) -> DetectedVerb | None:
        normalized = normalize_text(text)
        matches: list[DetectedVerb] = []
        for form, strength in self.verb_forms:
            normalized_form = normalize_text(form)
            match = re.search(rf"(?<!\w){re.escape(normalized_form)}(?!\w)", normalized)
            if match:
                matches.append(DetectedVerb(form, strength, match.start()))
        return min(matches, key=lambda item: item.position) if matches else None

    def _excluded(self, sentence: str) -> bool:
        normalized = normalize_text(sentence)
        for pattern in self.rules.get("excluded_patterns", []):
            raw_pattern = str(pattern)
            normalized_pattern = normalize_text(raw_pattern)
            if raw_pattern in sentence or (
                normalized_pattern and normalized_pattern in normalized
            ):
                return True
        chunks = [chunk.strip() for chunk in sentence.split(",")]
        if len(chunks) >= 4 and sum(len(chunk.split()) for chunk in chunks[:4]) <= 10:
            return True
        return not normalized

    def _future_consequence_as_fact(self, sentence: str) -> bool:
        normalized = normalize_text(sentence)
        future_positions = [
            normalized.find(normalize_text(str(pattern)))
            for pattern in self.rules.get("future_consequence_patterns", [])
            if normalize_text(str(pattern)) in normalized
        ]
        if not future_positions:
            return False
        first_future = min(future_positions)
        return not any(
            0 <= normalized.find(normalize_text(str(form))) < first_future
            for form in self.rules.get("attribution_forms", [])
        )

    def _neutral_main(self, publication: Publication, actor_names: list[str]) -> str:
        actor = self._join_spanish(actor_names) if actor_names else ""
        event_phrase = self.rules.get("event_phrases", {}).get(
            publication.event_type_detected,
            "un hecho electoral",
        )
        state = publication.state_detected
        if actor and state:
            return f"{actor} fue referido en el contexto de {event_phrase} en {state}"
        if actor:
            return f"{actor} fue mencionado en relación con {event_phrase}"
        if state:
            return f"Se reportó {event_phrase} en {state}"
        return f"Se registró información sobre {event_phrase}"

    def _ensure_actor(self, main: str, title: str, actor_names: list[str]) -> str:
        if not actor_names or self._contains_actor(main, actor_names):
            return main
        if self._contains_actor(title, actor_names):
            return title
        return f"{self._join_spanish(actor_names)}: {main[:1].lower()}{main[1:]}"

    def _fit_main(self, main: str, context: str) -> str:
        available = max(4, self.maximum_words - self._word_count(context))
        words = main.strip(" .").split()
        if len(words) <= available:
            return " ".join(words)
        # Try to cut at the last clause boundary within the word limit.
        truncated = " ".join(words[:available])
        for separator in (";", ",", " que ", " donde ", " cuando "):
            pos = truncated.rfind(separator)
            if pos > len(truncated) // 3:
                truncated = truncated[:pos].strip()
                break
        else:
            # Fallback: remove trailing function words (prepositions, articles,
            # conjunctions) that leave the sentence dangling.
            result_words = truncated.split()
            _trailing_noise = {
                "de", "del", "a", "al", "con", "en", "por", "para",
                "que", "y", "la", "el", "lo", "las", "los", "un", "una",
            }
            while result_words and result_words[-1].lower() in _trailing_noise:
                result_words.pop()
            truncated = " ".join(result_words)
        return truncated

    def _enforce_limits(
        self, summary: str, backup_sentences: list[str] | None = None,
    ) -> str:
        words = summary.split()
        if len(words) > self.maximum_words:
            words = words[: self.maximum_words]
            summary = " ".join(words).rstrip(" ,;:") + "."
        if len(words) < self.minimum_words:
            # Try to insert a supporting sentence from the article body.
            extended = False
            if backup_sentences:
                for candidate in backup_sentences:
                    candidate_text = candidate.strip(" .")
                    attempt = summary.rstrip(".") + "; " + candidate_text[:1].lower() + candidate_text[1:] + "."
                    if len(attempt.split()) <= self.maximum_words:
                        summary = attempt
                        extended = True
                        break
            if not extended:
                supplement = " según lo publicado por la fuente consultada"
                summary = summary.rstrip(".") + supplement + "."
                words = summary.split()
                if len(words) > self.maximum_words:
                    summary = " ".join(words[: self.maximum_words]).rstrip(" ,;:") + "."
        return summary

    @staticmethod
    def _sentences(text: str) -> list[str]:
        clean = SummaryGenerator._clean(text)
        clean = re.sub(r"\bRead more\b.*$", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\bThe post\b.*$", "", clean, flags=re.IGNORECASE)
        return [part.strip(" -–—") for part in re.split(r"(?<=[.!?])\s+", clean) if part.strip()]

    @staticmethod
    def _clean(text: str) -> str:
        value = html.unescape(text or "")
        value = re.sub(r"<[^>]+>", " ", value)
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _word_count(text: str) -> int:
        return len(re.findall(r"\b[\wÁÉÍÓÚÜÑáéíóúüñ]+\b", text))

    @staticmethod
    def _as_sentence(text: str) -> str:
        text = text.strip(" .")
        return f"{text}." if text else ""

    @staticmethod
    def _contains_term(text: str, term: str) -> bool:
        normalized_text = normalize_text(text)
        normalized_term = normalize_text(term)
        return bool(normalized_term) and bool(
            re.search(rf"(?<!\w){re.escape(normalized_term)}(?!\w)", normalized_text)
        )

    @classmethod
    def _contains_actor(cls, text: str, actor_names: list[str]) -> bool:
        return any(cls._contains_term(text, name) for name in actor_names)

    @staticmethod
    def _actor_value(actors: list[Actor], attribute: str) -> str | None:
        return next((str(value) for actor in actors if (value := getattr(actor, attribute))), None)

    @staticmethod
    def _join_spanish(items: list[str]) -> str:
        unique = list(dict.fromkeys(items))
        if len(unique) <= 1:
            return unique[0] if unique else ""
        return ", ".join(unique[:-1]) + f" y {unique[-1]}"
