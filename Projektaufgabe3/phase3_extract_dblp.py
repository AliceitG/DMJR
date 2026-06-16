#!/usr/bin/env python3
"""
Schritt 1 von Phase 3:
Extrahiert alle VLDB-, SIGMOD- und ICDE-Publikationen aus dblp.xml
und schreibt sie in my_small_bib.xml.

Verwendung:
    python phase3_extract_dblp.py [dblp.xml] [my_small_bib.xml]

Standardpfade:
    dblp.xml        → dblp.xml (im aktuellen Verzeichnis)
    my_small_bib.xml → my_small_bib.xml (im aktuellen Verzeichnis)

Voraussetzungen:
    pip install lxml
"""

import sys
from pathlib import Path
from lxml import etree

# Venue-Präfixe gemäß Aufgabenstellung
VENUE_PREFIXES = [
    ('journals/pvldb/', 'vldb'),
    ('conf/vldb/',      'vldb'),
    ('journals/pacmmod/', 'sigmod'),
    ('conf/sigmod/',    'sigmod'),
    ('conf/icde/',      'icde'),
]

# Nur article und inproceedings-Elemente werden berücksichtigt
RECORD_TAGS = {'article', 'inproceedings'}


def get_venue(key: str) -> str | None:
    for prefix, venue in VENUE_PREFIXES:
        if key.startswith(prefix):
            return venue
    return None


def extract_dblp(dblp_path: Path, output_path: Path) -> dict[str, int]:
    counts = {'vldb': 0, 'sigmod': 0, 'icde': 0}

    with open(output_path, 'wb') as out:
        out.write(b'<?xml version="1.0" encoding="utf-8"?>\n<bib>\n')

        context = etree.iterparse(
            str(dblp_path),
            events=('end',),
            load_dtd=True,
            resolve_entities=True,
            no_network=True,
        )

        for _, elem in context:
            if elem.tag not in RECORD_TAGS:
                # Nicht-relevante Elemente sofort freigeben
                elem.clear()
                while elem.getprevious() is not None:
                    del elem.getparent()[0]
                continue

            key = elem.get('key', '')
            venue = get_venue(key)
            if venue is not None:
                out.write(b'  ')
                out.write(etree.tostring(elem, encoding='unicode').encode('utf-8'))
                out.write(b'\n')
                counts[venue] += 1

            # Element aus Speicher entfernen
            elem.clear()
            while elem.getprevious() is not None:
                del elem.getparent()[0]

        out.write(b'</bib>\n')

    return counts


def count_augsten_per_venue(output_path: Path) -> dict[str, int]:
    """Zählt Publikationen von Nikolaus Augsten pro Venue in my_small_bib.xml."""
    counts = {'vldb': 0, 'sigmod': 0, 'icde': 0}

    for _, elem in etree.iterparse(str(output_path), events=('end',), tag=list(RECORD_TAGS)):
        key = elem.get('key', '')
        venue = get_venue(key)
        if venue is None:
            elem.clear()
            continue
        for author_elem in elem.findall('author'):
            if author_elem.text and 'Nikolaus Augsten' in author_elem.text:
                counts[venue] += 1
                break
        elem.clear()

    return counts


def verify_toy_example(output_path: Path, toy_keys: list[str]) -> dict[str, bool]:
    """Prüft ob die Toy-Beispiel-Artikel in my_small_bib.xml enthalten sind."""
    found = {k: False for k in toy_keys}

    for _, elem in etree.iterparse(str(output_path), events=('end',), tag=list(RECORD_TAGS)):
        key = elem.get('key', '')
        short_key = key.split('/')[-1]
        if short_key in found:
            found[short_key] = True
        elem.clear()

    return found


if __name__ == '__main__':
    dblp_path  = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('dblp.xml')
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('my_small_bib.xml')

    if not dblp_path.exists():
        print(f'FEHLER: {dblp_path} nicht gefunden.')
        print('Bitte dblp.xml.gz herunterladen und entpacken:')
        print('  wget https://dblp.org/xml/dblp.xml.gz && gunzip dblp.xml.gz')
        sys.exit(1)

    print(f'Lese {dblp_path} (ca. 4 GB, das kann einige Minuten dauern) ...')
    counts = extract_dblp(dblp_path, output_path)

    print(f'\nExtrahierte Publikationen in {output_path}:')
    total = 0
    for venue, n in counts.items():
        print(f'  {venue.upper():8s}: {n:6d}')
        total += n
    print(f'  {"GESAMT":8s}: {total:6d}')

    # Korrektheitsprüfung: Toy-Beispiel-Schlüssel
    toy_keys = ['SchmittKAMM23', 'HutterAK0L22', 'ThielKAHMS23', 'SchalerHS23']
    print('\nKorrektheitsprüfung – Toy-Beispiel-Artikel in my_small_bib.xml:')
    found = verify_toy_example(output_path, toy_keys)
    for key, present in found.items():
        status = 'OK' if present else 'FEHLT'
        print(f'  [{status}] {key}')

    # Anzahl Publikationen von Nikolaus Augsten
    print('\nPublikationen von Nikolaus Augsten pro Venue:')
    augsten = count_augsten_per_venue(output_path)
    for venue, n in augsten.items():
        print(f'  {venue.upper():8s}: {n}')
