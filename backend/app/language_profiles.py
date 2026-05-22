"""Language metadata used by the UI and backend.

Each profile tells RadioWatch whether Whisper can receive a language hint and
whether lemma matching is realistic with an available spaCy model.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class LanguageProfile:
    code: str
    name_english: str
    name_native: str
    whisper_code: str
    spacy_model: str | None
    spacy_install_command: str | None
    lemma_supported: bool
    is_rtl: bool = False


def _profile(code: str, english: str, native: str, model: str | None, rtl: bool = False) -> LanguageProfile:
    # Small helper keeps the table readable while still storing explicit data.
    command = f"python -m spacy download {model}" if model else None
    return LanguageProfile(code, english, native, code, model, command, model is not None, rtl)


LANGUAGE_PROFILES: dict[str, LanguageProfile] = {
    "es": _profile("es", "Spanish", "Español", "es_core_news_sm"),
    "fr": _profile("fr", "French", "Français", "fr_core_news_sm"),
    "de": _profile("de", "German", "Deutsch", "de_core_news_sm"),
    "pt": _profile("pt", "Portuguese", "Português", "pt_core_news_sm"),
    "it": _profile("it", "Italian", "Italiano", "it_core_news_sm"),
    "nl": _profile("nl", "Dutch", "Nederlands", "nl_core_news_sm"),
    "ru": _profile("ru", "Russian", "Русский", "ru_core_news_sm"),
    "zh": _profile("zh", "Chinese", "中文", "zh_core_web_sm"),
    "ar": _profile("ar", "Arabic", "العربية", None, True),
    "fa": _profile("fa", "Persian", "فارسی", None, True),
    "he": _profile("he", "Hebrew", "עברית", None, True),
    "ur": _profile("ur", "Urdu", "اردو", None, True),
    "tr": _profile("tr", "Turkish", "Türkçe", "tr_core_news_trf"),
    "en": _profile("en", "English", "English", "en_core_web_sm"),
}


def profiles_as_api() -> list[dict]:
    # Convert Python dataclasses to JSON-friendly keys used by the frontend.
    return [
        {
            "code": item["code"],
            "nameEnglish": item["name_english"],
            "nameNative": item["name_native"],
            "whisperCode": item["whisper_code"],
            "spaCyModel": item["spacy_model"],
            "spaCyInstallCommand": item["spacy_install_command"],
            "lemmaSupported": item["lemma_supported"],
            "isRtl": item["is_rtl"],
        }
        for item in (asdict(profile) for profile in LANGUAGE_PROFILES.values())
    ]

