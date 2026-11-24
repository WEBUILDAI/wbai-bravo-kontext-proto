from bravo_kontext.filter import redact


def test_redact_rekursiv():
    daten = {"kunde": "a", "x": [{"projekt": "p", "y": 1}], "z": ({"kunde": 1},)}
    assert redact(daten) == {"x": [{"y": 1}], "z": [{}]}
