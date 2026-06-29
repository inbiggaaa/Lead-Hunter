from app.locales.ru import TEXTS as RU
from app.locales.en import TEXTS as EN


_LOCALES = {"ru": RU, "en": EN}


def get_text(lang: str, key: str, **kwargs) -> str:
    """Get localized text by key, with optional format kwargs."""
    texts = _LOCALES.get(lang, _LOCALES["ru"])
    text = texts.get(key, key)
    if kwargs:
        return text.format(**kwargs)
    return text
