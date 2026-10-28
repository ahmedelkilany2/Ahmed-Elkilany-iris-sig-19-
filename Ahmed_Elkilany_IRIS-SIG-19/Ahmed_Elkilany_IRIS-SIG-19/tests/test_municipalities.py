import pytest

from gazette_harvester.municipalities import municipalities_from_title


@pytest.mark.parametrize(
    "title, slug, expected, inferred",
    [
        ("Gemeindenachrichten Amtsblatt der Gemeinden Bammental, Wiesenbach und Gaiberg", "x",
         ["Bammental", "Wiesenbach", "Gaiberg"], False),
        ("Mitteilungsblatt der Gemeinden Wehingen, Reichenbach a. H., Egesheim", "x",
         ["Wehingen", "Reichenbach a. H.", "Egesheim"], False),
        ("Amtsblatt Nachrichten der Gemeinde Schwieberdingen", "x", ["Schwieberdingen"], False),
        ("Amtsblatt der Stadt Ellwangen mit den Ortsteilen Pfahlheim und Rindelbach", "x", ["Ellwangen"], False),
        ("Amtsblatt Bartenbacher Informationen", "amtsblatt-bartenbach", ["Bartenbach"], True),
        ("Irgendwas", "", [], True),
    ],
)
def test_titles(title, slug, expected, inferred):
    assert municipalities_from_title(title, slug) == (expected, inferred)
