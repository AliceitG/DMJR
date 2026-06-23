#!/usr/bin/env python3
"""
Phase 3 - Benchmark, Vorbereitung: Datenbestand vergroessern.

Erhoeht den Datenbestand aus my_small_bib.xml um das Mehrfache, indem beim
Parsen von dblp.xml zusaetzliche Venues beruecksichtigt werden (frei gewaehlt,
siehe TIERS unten). Tier 1 entspricht genau den Venues aus my_small_bib.xml
(vldb, sigmod, icde) und ist damit gleich gross wie der Datenbestand aus
Phase 2. Die Tiers sind kumulativ: bench_size2.xml enthaelt bench_size1.xml
plus die zusaetzlichen Venues von Tier 2, usw.

Die tatsaechliche Groesse jeder Stufe wird beim Lauf ausgegeben und gilt als
Basis fuer den Benchmark (keine exakten Verdopplungen erzwungen).

Verwendung:
    python Phase3_Benchmark_Extract.py [dblp.xml] [output_dir]
"""

import sys
from pathlib import Path

from lxml import etree

RECORD_TAGS = {'article', 'inproceedings'}

# Tier 1 = exakt die Venues aus my_small_bib.xml (Basis, "tatsaechliche Groesse").
# Tier 2-4 fuegen weitere, frei gewaehlte Venues hinzu um den Datenbestand zu
# vergroessern. Jeder Eintrag: (key-Praefix, Venue-Name, Tier).
TIERED_VENUE_PREFIXES = [
    # --- Tier 1 (Basis, identisch zu my_small_bib.xml) ---
    ('journals/pvldb/',   'vldb',   1),
    ('conf/vldb/',        'vldb',   1),
    ('journals/pacmmod/', 'sigmod', 1),
    ('conf/sigmod/',      'sigmod', 1),
    ('conf/icde/',        'icde',   1),
    # --- Tier 2 (zusaetzliche DB/Web-Venues, ~Verdopplung) ---
    ('conf/cidr/',         'cidr',  2),
    ('conf/edbt/',         'edbt',  2),
    ('journals/tods/',     'tods',  2),
    ('conf/icdt/',         'icdt',  2),
    ('conf/kdd/',          'kdd',   2),
    ('conf/www/',          'www',   2),
    # --- Tier 3 (groessere IR/AI-Venues, ~Vervierfachung) ---
    ('conf/sigir/',        'sigir', 3),
    ('conf/aaai/',         'aaai',  3),
    # --- Tier 4 (sehr grosse AI/Vision-Venues, ~Verachtfachung) ---
    ('conf/cvpr/',         'cvpr',  4),
    ('conf/nips/',         'nips',  4),
]

MAX_TIER = max(tier for _, _, tier in TIERED_VENUE_PREFIXES)


def classify(key: str):
    """Liefert (venue, tier) fuer einen DBLP-Key oder (None, None)."""
    for prefix, venue, tier in TIERED_VENUE_PREFIXES:
        if key.startswith(prefix):
            return venue, tier
    return None, None


def extract_tiers(dblp_path: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    handles = {}
    counts = {tier: 0 for tier in range(1, MAX_TIER + 1)}
    per_venue_counts = {}

    for tier in range(1, MAX_TIER + 1):
        path = output_dir / f'bench_size{tier}.xml'
        handle = open(path, 'wb')
        handle.write(b'<?xml version="1.0" encoding="utf-8"?>\n<bib>\n')
        handles[tier] = handle

    context = etree.iterparse(
        str(dblp_path),
        events=('end',),
        tag=list(RECORD_TAGS),
        load_dtd=True,
        resolve_entities=True,
        no_network=True,
    )

    processed = 0
    for _, elem in context:
        key = elem.get('key', '')
        venue, tier = classify(key)
        if venue is not None:
            serialized = etree.tostring(elem, encoding='unicode').encode('utf-8')
            # Kumulativ: ein Datensatz von Tier t landet in allen Dateien >= t.
            for target_tier in range(tier, MAX_TIER + 1):
                handles[target_tier].write(b'  ')
                handles[target_tier].write(serialized)
                handles[target_tier].write(b'\n')
                counts[target_tier] += 1
            per_venue_counts[venue] = per_venue_counts.get(venue, 0) + 1

        elem.clear()
        while elem.getprevious() is not None:
            del elem.getparent()[0]

        processed += 1
        if processed % 200000 == 0:
            print(f'  ... {processed} Datensaetze aus dblp.xml gescannt')

    for tier, handle in handles.items():
        handle.write(b'</bib>\n')
        handle.close()

    return {'counts': counts, 'per_venue_counts': per_venue_counts}


if __name__ == '__main__':
    dblp_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('dblp.xml')
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('benchmark')

    if not dblp_path.exists():
        print(f'FEHLER: {dblp_path} nicht gefunden.')
        sys.exit(1)

    print(f'Lese {dblp_path} und extrahiere {MAX_TIER} gestufte Datenbestaende ...')
    result = extract_tiers(dblp_path, output_dir)

    print('\nTatsaechliche Groesse je Stufe (Basis = Stufe 1, entspricht my_small_bib.xml):')
    base = result['counts'][1]
    for tier, count in sorted(result['counts'].items()):
        factor = count / base if base else 0.0
        print(f'  bench_size{tier}.xml : {count:7d} Datensaetze (Faktor {factor:.2f}x)')

    print('\nDatensaetze pro Venue (ueber alle Tiers):')
    for venue, count in sorted(result['per_venue_counts'].items(), key=lambda kv: -kv[1]):
        print(f'  {venue:8s}: {count}')
