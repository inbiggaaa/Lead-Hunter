import logging
import string

from app.locales.ru import TEXTS as RU
from app.locales.en import TEXTS as EN

logger = logging.getLogger(__name__)
_LOCALES = {"ru": RU, "en": EN}
SUPPORTED_LANGUAGES = frozenset(_LOCALES)


def normalize_language(lang: str | None) -> str:
    """Return a supported language; invalid persisted values safely fall back to RU."""
    if lang in SUPPORTED_LANGUAGES:
        return lang
    logger.warning("Unsupported user language %r; falling back to ru", lang)
    return "ru"


def template_fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def validate_locale_schema() -> None:
    """Fail fast in tests/startup checks when RU/EN contracts diverge."""
    if RU.keys() != EN.keys():
        missing_en = sorted(RU.keys() - EN.keys())
        missing_ru = sorted(EN.keys() - RU.keys())
        raise ValueError(f"Locale key mismatch: missing_en={missing_en}, missing_ru={missing_ru}")
    mismatched = [key for key in RU if template_fields(RU[key]) != template_fields(EN[key])]
    if mismatched:
        raise ValueError(f"Locale placeholder mismatch: {mismatched}")


def get_text(lang: str | None, key: str, **kwargs) -> str:
    """Get localized text. Unknown keys are programming errors, never user output."""
    lang = normalize_language(lang)
    try:
        text = _LOCALES[lang][key]
    except KeyError as exc:
        raise KeyError(f"Unknown locale key: {key}") from exc
    return text.format(**kwargs) if kwargs else text
