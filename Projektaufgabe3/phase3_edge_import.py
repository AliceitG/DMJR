#!/usr/bin/env python3
"""
Schritt 2 von Phase 3:
Liest my_small_bib.xml, baut daraus den EDGE-Modell-Baum auf
und importiert ihn in PostgreSQL (Relationen node und edge).

Verwendung:
    python phase3_edge_import.py [my_small_bib.xml]

Datenbankschema (identisch mit phase1_tables.sql):
    node(id SERIAL PRIMARY KEY, s_id VARCHAR, type VARCHAR, content TEXT)
    edge("from" INTEGER, "to" INTEGER, PRIMARY KEY ("from","to"))

Am Ende werden die Tupelanzahlen in node und edge ausgegeben.
"""

import sys
from pathlib import Path

import psycopg2
from lxml import etree

# Datenbankverbindung – gleiche Konfiguration wie in phase1_import.py
DB_CONFIG = {
    'dbname':   'projektaufgabe1',
    'user':     'projektaufgabe1_user',
    'password': '1234',
    'host':     'localhost',
}

# Venue-Präfixe gemäß Aufgabenstellung
VENUE_PREFIXES = [
    ('journals/pvldb/', 'vldb'),
    ('conf/vldb/',      'vldb'),
    ('journals/pacmmod/', 'sigmod'),
    ('conf/sigmod/',    'sigmod'),
    ('conf/icde/',      'icde'),
]

# Felder, die als Blattknoten übernommen werden (wie in phase1_import.py)
ALLOWED_FIELDS = {
    'author', 'title', 'pages', 'year', 'volume',
    'journal', 'number', 'ee', 'url', 'booktitle', 'crossref',
}


def get_venue(key: str) -> str | None:
    for prefix, venue in VENUE_PREFIXES:
        if key.startswith(prefix):
            return venue
    return None


# ---------------------------------------------------------------------------
# Node-Klasse (identische Struktur wie in phase1_import.py)
# ---------------------------------------------------------------------------

class Node:
    def __init__(self, s_id, type_, content=None):
        self.s_id = s_id
        self.type = type_
        self.content = content
        self.children: list['Node'] = []
        self.db_id: int | None = None

    def add_child(self, child: 'Node') -> 'Node':
        self.children.append(child)
        return child

    def to_edge_model(self, cur, parent_id: int | None = None) -> None:
        cur.execute(
            'INSERT INTO node (s_id, type, content) VALUES (%s, %s, %s) RETURNING id',
            (self.s_id, self.type, self.content),
        )
        self.db_id = cur.fetchone()[0]

        if parent_id is not None:
            cur.execute(
                'INSERT INTO edge ("from", "to") VALUES (%s, %s)',
                (parent_id, self.db_id),
            )

        for child in self.children:
            child.to_edge_model(cur, self.db_id)


# ---------------------------------------------------------------------------
# Baum aufbauen
# ---------------------------------------------------------------------------

def build_node_tree(input_path: Path) -> Node:
    """
    Liest my_small_bib.xml (DBLP-Format) und baut den EDGE-Baum auf:
      bib
        venue (vldb | sigmod | icde)
          year (vldb_2023, ...)
            article|inproceedings (z.B. SchmittKAMM23)
              author: Daniel Ulrich Schmitt
              title:  ...
              ...
    """
    root = Node('bib', 'bib')
    venue_nodes: dict[str, Node] = {}
    year_nodes:  dict[tuple, Node] = {}

    RECORD_TAGS = {'article', 'inproceedings'}

    for _, elem in etree.iterparse(str(input_path), events=('end',), tag=list(RECORD_TAGS),
                                   load_dtd=True, resolve_entities=True, no_network=True):
        key    = elem.get('key', '')
        venue  = get_venue(key)
        if venue is None:
            elem.clear()
            continue

        year_elem = elem.find('year')
        year = (year_elem.text or '').strip() if year_elem is not None and year_elem.text else 'unknown'

        short_key = key.split('/')[-1]

        if venue not in venue_nodes:
            venue_nodes[venue] = root.add_child(Node(venue, 'venue'))

        year_key = (venue, year)
        if year_key not in year_nodes:
            year_nodes[year_key] = venue_nodes[venue].add_child(
                Node(f'{venue}_{year}', 'year')
            )

        pub_node = year_nodes[year_key].add_child(Node(short_key, elem.tag))

        for child in elem:
            if child.tag in ALLOWED_FIELDS:
                pub_node.add_child(Node(None, child.tag, (child.text or '').strip()))

        elem.clear()
        while elem.getprevious() is not None:
            del elem.getparent()[0]

    return root


# ---------------------------------------------------------------------------
# Datenbankimport
# ---------------------------------------------------------------------------

def import_to_db(root: Node) -> None:
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn:
            with conn.cursor() as cur:
                root.to_edge_model(cur, parent_id=None)
        print('Datenbankimport erfolgreich.')
    finally:
        conn.close()


def report_counts() -> None:
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM node;')
            node_count = cur.fetchone()[0]
            cur.execute('SELECT COUNT(*) FROM edge;')
            edge_count = cur.fetchone()[0]
        print(f'\nAnzahl Tupel in den Relationen:')
        print(f'  node: {node_count}')
        print(f'  edge: {edge_count}')
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    input_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('my_small_bib.xml')

    if not input_path.exists():
        print(f'FEHLER: {input_path} nicht gefunden.')
        print('Bitte zuerst phase3_extract_dblp.py ausführen.')
        sys.exit(1)

    print(f'Lese {input_path} und baue EDGE-Baum auf ...')
    root = build_node_tree(input_path)

    print('Importiere in Datenbank ...')
    try:
        import_to_db(root)
        report_counts()
    except Exception as e:
        print(f'Fehler beim DB-Import: {e}')
        sys.exit(1)
