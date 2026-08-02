from app.normalizers.text import content_hash, normalize_text, normalize_url


def test_normalize_text_removes_accents_case_and_extra_spacing() -> None:
    assert normalize_text("  Resolución   ELECTORAL, en México. ") == "resolucion electoral en mexico"


def test_normalize_url_removes_tracking_and_fragment() -> None:
    first = normalize_url("https://www.example.mx/nota/?utm_source=x&b=2&a=1#parte")
    second = normalize_url("https://example.mx/nota?a=1&b=2")
    assert first == second == "https://example.mx/nota?a=1&b=2"


def test_content_hash_is_stable_after_cosmetic_changes() -> None:
    assert content_hash("Encuesta", "Intención de voto") == content_hash(
        "ENCUESTA!", "intencion   de voto"
    )

