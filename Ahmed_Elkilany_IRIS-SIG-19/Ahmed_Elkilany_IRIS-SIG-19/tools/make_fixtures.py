"""Regenerates the HTML fixtures under tests/fixtures.

site/  mirrors the structure of the real Kiosk pages as I saw them rendered on 2026-10-27
       (reconstructed from the page text, NOT a byte-for-byte download; see README).
edge/  synthetic pages that exist only to exercise error handling.
"""
from pathlib import Path

HEAD = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<title>Kiosk - Publikation | NUSSBAUM.de</title>
<script>window.__cfg = {"a": "Ausgabe 99/2026 vom 01. Januar 2026"};</script></head><body>
<header><a href="/meine-heimat/startseite">NUSSBAUM</a> <a href="/kiosk/mitteilungsblaetter">Mitteilungsblätter</a>
<a href="/kiosk/sonderausgaben">Sonderausgaben</a> <button>Anmelden</button></header><main>"""
FOOT = """</main><footer><a href="/impressum">Impressum</a> <a href="https://abo.nussbaum.de/">Abo abschließen</a>
<p>Ein Angebot von NUSSBAUM Medien.</p></footer></body></html>"""
ZW = '<a href="/meine-heimat/undefined">\u200c \u200c \u200c</a>'


def block(label, date, paid=True, current=False):
    h = f"Aktuell: {label}" if current else label
    badge = '<span class="badge">NUSSBAUM+</span>' if paid else ""
    extra = '<a href="#">Ausgabe lesen</a><button>Herunterladen</button>' if current else ""
    return (f'<h2>{h}</h2><p>{date}</p>{badge}{extra}'
            f'<img alt="{label} lesen" src="https://example.invalid/thumb.png">\n')


def page(title, blocks, tail=""):
    out = [f"<h1>{title}</h1>\n"]
    for i, b in enumerate(blocks):
        if i == 1:
            out.append("<h2>Bisherige Ausgaben</h2>\n")
        out.append(b)
        if i % 3 == 2:
            out.append(ZW)
    return HEAD + "".join(out) + tail + "<button>Mehr anzeigen</button>" + FOOT


def main():
    site, edge = Path("tests/fixtures/site"), Path("tests/fixtures/edge")
    site.mkdir(parents=True, exist_ok=True)
    edge.mkdir(parents=True, exist_ok=True)

    bammental = [("43", "21. Oktober"), ("42", "14. Oktober"), ("41", "07. Oktober"), ("40", "30. September"),
                 ("39", "23. September"), ("38", "16. September"), ("37", "09. September"), ("36", "02. September"),
                 ("35", "26. August"), ("34", "19. August"), ("33", "12. August"), ("32", "05. August"), ("31", "29. Juli")]
    blocks = [block(f"Ausgabe {n}/2026", f"vom {d} 2026", True, current=(i == 0)) for i, (n, d) in enumerate(bammental)]
    (site / "kiosk_mitteilungsblaetter_amtsblatt-bammental.html").write_text(
        page("Gemeindenachrichten Amtsblatt der Gemeinden Bammental, Wiesenbach und Gaiberg", blocks), encoding="utf-8")

    wehingen = [("30", "22. Juli"), ("29", "15. Juli"), ("28", "08. Juli"), ("27", "01. Juli"), ("26", "24. Juni"),
                ("25", "17. Juni"), ("24", "10. Juni"), ("23", "02. Juni"), ("22", "27. Mai"), ("21", "20. Mai"),
                ("20", "12. Mai"), ("19", "06. Mai")]
    blocks = [block(f"Ausgabe {n}/2026", f"vom {d} 2026", True, current=(i == 0)) for i, (n, d) in enumerate(wehingen)]
    (site / "kiosk_mitteilungsblaetter_amtsblatt-wehingen.html").write_text(
        page("Mitteilungsblatt der Gemeinden Wehingen, Reichenbach a. H., Egesheim", blocks), encoding="utf-8")

    (site / "kiosk_mitteilungsblaetter.html").write_text(
        HEAD + """<h1>Mitteilungsblätter</h1><ul>
<li><a href="/kiosk/mitteilungsblaetter/amtsblatt-bammental">Gemeindenachrichten Bammental</a></li>
<li><a href="/kiosk/mitteilungsblaetter/amtsblatt-wehingen?x=1">Mitteilungsblatt Wehingen</a></li>
<li><a href="/kiosk/mitteilungsblaetter/amtsblatt-bammental#top">Bammental (again)</a></li>
<li><a href="/kiosk/sonderausgaben">Sonderausgaben</a></li>
<li><a href="https://elsewhere.example/kiosk/mitteilungsblaetter/x">other host</a></li></ul>""" + FOOT,
        encoding="utf-8")

    blocks = [
        block("Ausgabe 10/2026", "vom 04. März 2026", paid=False),
        block("Ausgabe 11/2026", "vom 11. März 2026", paid=True),
        block("Ausgabe 12/2026", "vom 31. Februar 2026", paid=True),   # impossible date
        block("Ausgabe 13/2026", "vom 18. Smarch 2026", paid=True),    # unknown month
        block("Ausgabe 50/2026", "vom 30. Dezember 2026", paid=True),  # after "today" in the tests
        block("Ausgabe 10/2026", "vom 04. März 2026", paid=False),     # duplicate
        block("Ausgabe 14/2026", "bald", paid=True),                   # no date at all
        block("Ausgabe 20/2026", "vom 15. April 2026", paid=False),    # calendar week 16, issue says 20
    ]
    filler = "".join(f"<p>{c}</p>" for c in "abcdefgh") + "<p>NUSSBAUM+</p>"  # footer text must not leak into the last issue
    (edge / "kiosk_mitteilungsblaetter_amtsblatt-musterstadt.html").write_text(
        page("Amtsblatt Musterstadt Aktuell", blocks, tail=filler), encoding="utf-8")
    (edge / "kiosk_mitteilungsblaetter_empty-page.html").write_text("", encoding="utf-8")
    (edge / "kiosk_mitteilungsblaetter_no-title.html").write_text(
        HEAD + block("Ausgabe 1/2026", "vom 07. Januar 2026") + FOOT, encoding="utf-8")
    (edge / "kiosk_mitteilungsblaetter_no-issues.html").write_text(
        HEAD + "<h1>Amtsblatt Leerhausen</h1><p>Keine Ausgaben</p>" + FOOT, encoding="utf-8")


if __name__ == "__main__":
    main()
