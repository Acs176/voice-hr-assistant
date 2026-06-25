import pytest

from cs_voice.parsing import parse_employee_id


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("ORB1234", "ORB1234"),
        ("orb1234", "ORB1234"),
        ("ORB 1234", "ORB1234"),
        ("ORB-1234", "ORB1234"),
        # STT spells letters individually with spaces.
        ("O R B 1 2 3 4", "ORB1234"),
        # Filler / sentence-style surrounding the ID.
        ("um, my id is ORB 1234", "ORB1234"),
        ("I think it's ORB1234", "ORB1234"),
        ("ORB 12 34", "ORB1234"),
        # Caller self-corrects: last ORB-pattern wins.
        ("it's ORB1234, wait no, ORB1237", "ORB1237"),
        # Diacritics from non-English STT output get normalized to ASCII.
        ("creo que es ÓRB1234", "ORB1234"),
    ],
)
def test_parses_valid_ids(raw: str, expected: str) -> None:
    result = parse_employee_id(raw)
    assert result.ok, result.error
    assert result.value == expected


@pytest.mark.parametrize(
    "raw, expected_error_fragment",
    [
        ("ORB123", "3 digit"),  # too short
        ("ORB12345", "5 digit"),  # too long
        ("XYZ1234", "missing 'ORB' prefix"),
        ("", "empty"),
        ("   ", "empty"),
        ("no idea", "missing 'ORB' prefix"),
    ],
)
def test_rejects_invalid_ids(raw: str, expected_error_fragment: str) -> None:
    result = parse_employee_id(raw)
    assert not result.ok
    assert result.error is not None
    assert expected_error_fragment in result.error
