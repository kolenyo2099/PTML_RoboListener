"""Keyword matching for transcript chunks.

The matcher supports exact, fuzzy, and lemma modes. Lemma mode uses a spaCy
model only when one is available and installed for the station language.
"""

from __future__ import annotations

from rapidfuzz import fuzz

from .language_profiles import LANGUAGE_PROFILES
from .models import KeywordConfig


class KeywordMatcher:
    def __init__(self) -> None:
        self._models: dict[str, object | None] = {}

    def load_for_languages(self, language_codes: set[str]) -> None:
        # spaCy models are loaded once per language. Missing models are recorded
        # as None so the backend can fall back to exact matching without retrying.
        for code in language_codes:
            if code in self._models:
                continue
            profile = LANGUAGE_PROFILES.get(code)
            if not profile or not profile.spacy_model:
                self._models[code] = None
                continue
            try:
                import spacy

                self._models[code] = spacy.load(profile.spacy_model)
            except Exception:
                self._models[code] = None

    def loaded_models(self) -> list[str]:
        loaded = []
        for code, model in self._models.items():
            profile = LANGUAGE_PROFILES.get(code)
            if model and profile and profile.spacy_model:
                loaded.append(profile.spacy_model)
        return sorted(loaded)

    def find_matches(self, text: str, language_code: str, config: KeywordConfig) -> tuple[list[str], str, str | None]:
        text_lower = text.lower()
        matches: list[str] = []
        mode_used = config.matchMode
        spacy_model_used: str | None = None

        if config.matchMode == "fuzzy":
            for keyword in config.keywords:
                if fuzz.partial_ratio(keyword.text.lower(), text_lower) >= config.fuzzyThreshold:
                    matches.append(keyword.text)
            return matches, "fuzzy", None

        if config.matchMode == "lemma":
            model = self._models.get(language_code)
            profile = LANGUAGE_PROFILES.get(language_code)
            if model and profile:
                transcript_lemmas = {token.lemma_.lower() for token in model(text)}
                for keyword in config.keywords:
                    keyword_lemmas = {token.lemma_.lower() for token in model(keyword.text)}
                    if keyword_lemmas and keyword_lemmas.issubset(transcript_lemmas):
                        matches.append(keyword.text)
                spacy_model_used = profile.spacy_model
                return matches, "lemma", spacy_model_used
            mode_used = "exact-fallback"

        for keyword in config.keywords:
            if keyword.text.lower() in text_lower:
                matches.append(keyword.text)
        return matches, mode_used, spacy_model_used

