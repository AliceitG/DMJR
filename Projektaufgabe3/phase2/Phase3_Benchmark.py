#!/usr/bin/env python3
"""
Phase 3 - Benchmark (1 Punkt).

Vergleicht vier Zugriffsstrategien auf wachsenden Datenbestaenden:

  A. EDGE-Modell (Phase 1)            - WITH RECURSIVE auf node/edge,
                                         mit Indexen auf edge(from)/edge(to).
  B. XPath Accelerator (Phase 2)      - volles pre/post-Fenster auf accel,
                                         mit GiST/R-Baum-Index auf der bbox-Spalte.
  C. XPath Accelerator (Phase 3)      - verkleinertes Fenster (Baumhoehe-
                                         beschraenkt) auf derselben accel-Tabelle
                                         und demselben R-Baum-Index.
  D. 1D-Accelerator (Phase 3)         - nur descendant-Achse, ein Zaehler,
                                         geclusterter B+-Baum auf pre.

Anfragen (siehe Aufgabenstellung):
  - ancestor-Achse:            Kontextknoten = zufaelliger article/inproceedings-Knoten
  - descendant-Achse:          Kontextknoten = zufaelliger year-Knoten
  - following/preceding-sibl.: Kontextknoten = zufaelliger article/inproceedings-Knoten,
                                Richtung wird je Knoten ausgewuerfelt

Datenbestand: bench_size1.xml ... bench_sizeN.xml (siehe Phase3_Benchmark_Extract.py),
Stufe 1 entspricht der tatsaechlichen Groesse von my_small_bib.xml.

Verwendung:
    python Phase3_Benchmark.py [benchmark_dir] [num_samples]
"""

import json
import random
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

from Phase2_Annotierungsfunktion import annotate_xml

db_config = {
    "dbname": "projektaufgabe1",
    "user": "projektaufgabe1_user",
    "password": "1234",
    "host": "localhost",
}

RESULTS_DIR = Path(__file__).resolve().parent / "benchmark_results"

ALLOWED_FIELDS = {
    'author', 'title', 'pages', 'year', 'volume',
    'journal', 'number', 'ee', 'url', 'booktitle', 'crossref',
}

# Erweiterte Venue-Zuordnung, deckt alle in Phase3_Benchmark_Extract.py
# verwendeten Tiers ab. Jeder Praefix wird 1:1 zu seinem eigenen Venue-Knoten.
VENUE_PREFIXES = [
    ('journals/pvldb/',   'vldb'),
    ('conf/vldb/',        'vldb'),
    ('journals/pacmmod/', 'sigmod'),
    ('conf/sigmod/',      'sigmod'),
    ('conf/icde/',        'icde'),
    ('conf/cidr/',        'cidr'),
    ('conf/edbt/',        'edbt'),
    ('journals/tods/',    'tods'),
    ('conf/icdt/',        'icdt'),
    ('conf/kdd/',         'kdd'),
    ('conf/www/',         'www'),
    ('conf/sigir/',       'sigir'),
    ('conf/aaai/',        'aaai'),
    ('conf/cvpr/',        'cvpr'),
    ('conf/nips/',        'nips'),
]


def _venue(key: str):
    for prefix, venue in VENUE_PREFIXES:
        if key.startswith(prefix):
            return venue
    return None


# ---------------------------------------------------------------------------
# Baum aufbauen (bib -> venue -> year -> article/inproceedings -> Felder)
# ---------------------------------------------------------------------------

def build_edge_root(input_path: Path) -> ET.Element:
    import lxml.etree as LET

    edge_root = ET.Element('bib')
    venue_nodes = {}
    year_nodes = {}

    context = LET.iterparse(
        str(input_path), events=('end',), tag=('article', 'inproceedings'),
        load_dtd=False, resolve_entities=False, no_network=True,
    )
    for _, elem in context:
        key = elem.get('key', '')
        venue = _venue(key) or 'unknown'
        year_elem = elem.find('year')
        year = (year_elem.text or '').strip() if year_elem is not None and year_elem.text else 'unknown'
        short_key = key.split('/')[-1] if key else elem.tag

        if venue not in venue_nodes:
            venue_nodes[venue] = ET.SubElement(edge_root, 'venue', {'name': venue})

        ykey = (venue, year)
        if ykey not in year_nodes:
            year_nodes[ykey] = ET.SubElement(venue_nodes[venue], 'year', {'value': year})

        pub_elem = ET.SubElement(year_nodes[ykey], elem.tag, {'key': short_key})
        for child in elem:
            if child.tag in ALLOWED_FIELDS:
                field = ET.SubElement(pub_elem, child.tag)
                field.text = (child.text or '').strip()

        elem.clear()
        while elem.getprevious() is not None:
            del elem.getparent()[0]

    return edge_root


def tree_height(elem) -> int:
    children = list(elem)
    if not children:
        return 0
    return 1 + max(tree_height(child) for child in children)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def setup_schema(conn):
    with conn.cursor() as cur:
        cur.execute("""
            DROP TABLE IF EXISTS bench_edge, bench_node, bench_accel,
                bench_content, bench_attribute, bench_accel1d CASCADE;

            CREATE TABLE bench_node (
                id      INTEGER PRIMARY KEY,
                s_id    TEXT,
                type    TEXT NOT NULL,
                content TEXT
            );
            CREATE TABLE bench_edge (
                "from" INTEGER NOT NULL,
                "to"   INTEGER NOT NULL,
                PRIMARY KEY ("from", "to")
            );

            CREATE TABLE bench_accel (
                pre    INTEGER PRIMARY KEY,
                post   INTEGER,
                parent INTEGER,
                kind   TEXT,
                name   TEXT,
                bbox   box GENERATED ALWAYS AS (box(point(pre, post), point(pre, post))) STORED
            );
            CREATE TABLE bench_content   (pre INTEGER, text TEXT);
            CREATE TABLE bench_attribute (pre INTEGER, text TEXT);

            CREATE TABLE bench_accel1d (
                pre    INTEGER PRIMARY KEY,
                post   INTEGER,
                parent INTEGER,
                kind   TEXT,
                name   TEXT
            );
        """)
    conn.commit()


def load_dataset(conn, accel_rows, content_rows, attribute_rows):
    node_rows = []
    edge_rows = []
    s_id_by_pre = {}
    for pre, text in attribute_rows:
        # key=..., name=..., value=... -> als s_id uebernehmen
        s_id_by_pre.setdefault(pre, text.split('=', 1)[-1])
    content_by_pre = {pre: text for pre, text in content_rows}

    for pre, post, parent, kind, name in accel_rows:
        content = content_by_pre.get(pre)
        s_id = s_id_by_pre.get(pre)
        node_rows.append((pre, s_id, name, content))
        if parent is not None:
            edge_rows.append((parent, pre))

    # page_size hochsetzen: execute_values verwendet sonst Batches von nur
    # 100 Zeilen, was bei Millionen Zeilen zu sehr vielen Round-Trips fuehrt.
    page_size = 10000
    with conn.cursor() as cur:
        execute_values(cur, "INSERT INTO bench_node (id, s_id, type, content) VALUES %s", node_rows, page_size=page_size)
        execute_values(cur, 'INSERT INTO bench_edge ("from", "to") VALUES %s', edge_rows, page_size=page_size)
        execute_values(cur, "INSERT INTO bench_accel (pre, post, parent, kind, name) VALUES %s", accel_rows, page_size=page_size)
        execute_values(cur, "INSERT INTO bench_content (pre, text) VALUES %s", content_rows, page_size=page_size)
        execute_values(cur, "INSERT INTO bench_attribute (pre, text) VALUES %s", attribute_rows, page_size=page_size)
        execute_values(cur, "INSERT INTO bench_accel1d (pre, post, parent, kind, name) VALUES %s", accel_rows, page_size=page_size)
    conn.commit()


def build_indexes(conn):
    with conn.cursor() as cur:
        # A. EDGE-Modell: Indexe fuer die rekursiven Joins in beide Richtungen.
        cur.execute('CREATE INDEX bench_edge_from_idx ON bench_edge ("from")')
        cur.execute('CREATE INDEX bench_edge_to_idx ON bench_edge ("to")')
        cur.execute('CLUSTER bench_node USING bench_node_pkey')

        # B/C. XPath Accelerator: B-Baum auf pre/post + R-Baum (GiST) auf bbox.
        cur.execute('CREATE INDEX bench_accel_pre_idx ON bench_accel (pre)')
        cur.execute('CREATE INDEX bench_accel_post_idx ON bench_accel (post)')
        cur.execute('CREATE INDEX bench_accel_parent_idx ON bench_accel (parent, pre)')
        cur.execute('CREATE INDEX bench_accel_bbox_gist ON bench_accel USING gist (bbox)')
        cur.execute('CREATE INDEX bench_attribute_text_idx ON bench_attribute (text)')

        # D. 1D-Accelerator: geclusterter B+-Baum auf pre (einzige Achse).
        cur.execute('CREATE INDEX bench_accel1d_pre_idx ON bench_accel1d (pre)')
        cur.execute('CLUSTER bench_accel1d USING bench_accel1d_pre_idx')

        cur.execute('ANALYZE bench_node; ANALYZE bench_edge; ANALYZE bench_accel; '
                    'ANALYZE bench_attribute; ANALYZE bench_accel1d;')
    conn.commit()


# ---------------------------------------------------------------------------
# Kontextknoten ziehen (einmal pro Datensatzgroesse und Achse, geteilt von
# allen vier Repraesentationen, da pre == id durch dieselbe DFS-Reihenfolge)
# ---------------------------------------------------------------------------

def sample_context_nodes(conn, num_samples, seed):
    rng = random.Random(seed)
    with conn.cursor() as cur:
        cur.execute("SELECT pre, post, parent FROM bench_accel "
                     "WHERE kind = 'element' AND name IN ('article', 'inproceedings')")
        article_nodes = cur.fetchall()
        # 'year' ist sowohl der Name des strukturellen Jahres-Knotens (Kind von
        # 'venue') als auch der Name des Blattfeldes <year> einer Publikation
        # (Kind von article/inproceedings). Nur erstere sind echte
        # Kontextknoten fuer die descendant-Achse.
        cur.execute("""
            SELECT y.pre, y.post, y.parent
            FROM   bench_accel y
            JOIN   bench_accel p ON p.pre = y.parent
            WHERE  y.kind = 'element' AND y.name = 'year' AND p.name = 'venue'
        """)
        year_nodes = cur.fetchall()

    ancestor_samples = rng.sample(article_nodes, min(num_samples, len(article_nodes)))
    descendant_samples = rng.sample(year_nodes, min(num_samples, len(year_nodes)))
    sibling_samples = rng.sample(article_nodes, min(num_samples, len(article_nodes)))
    sibling_samples = [(pre, post, parent, rng.choice(['following', 'preceding']))
                       for pre, post, parent in sibling_samples]

    return {
        'ancestor': ancestor_samples,
        'descendant': descendant_samples,
        'sibling': sibling_samples,
    }


# ---------------------------------------------------------------------------
# A. EDGE-Modell (rekursive CTE)
# ---------------------------------------------------------------------------

def edge_ancestor(cur, v_id):
    cur.execute("""
        WITH RECURSIVE anc AS (
            SELECT e."from" AS id FROM bench_edge e WHERE e."to" = %s
            UNION ALL
            SELECT e."from" FROM bench_edge e JOIN anc a ON e."to" = a.id
        )
        SELECT id FROM anc
    """, (v_id,))
    return cur.fetchall()


def edge_descendant(cur, v_id):
    cur.execute("""
        WITH RECURSIVE des AS (
            SELECT e."to" AS id FROM bench_edge e WHERE e."from" = %s
            UNION ALL
            SELECT e."to" FROM bench_edge e JOIN des d ON e."from" = d.id
        )
        SELECT id FROM des
    """, (v_id,))
    return cur.fetchall()


def edge_sibling(cur, v_id, parent_id, direction):
    op = '>' if direction == 'following' else '<'
    cur.execute(f"""
        SELECT e."to" AS id FROM bench_edge e
        WHERE e."from" = %s AND e."to" {op} %s
    """, (parent_id, v_id))
    return cur.fetchall()


# ---------------------------------------------------------------------------
# B. XPath Accelerator (Phase 2, volles Fenster, mit R-Baum)
# ---------------------------------------------------------------------------

INT_MIN, INT_MAX = -2147483648, 2147483647


def accel_ancestor_full(cur, pre_v, post_v):
    cur.execute("""
        SELECT pre FROM bench_accel
        WHERE bbox && box(point(%s, %s), point(%s, %s))
          AND pre < %s AND post > %s
    """, (INT_MIN, post_v + 1, pre_v - 1, INT_MAX, pre_v, post_v))
    return cur.fetchall()


def accel_descendant_full(cur, pre_v, post_v):
    cur.execute("""
        SELECT pre FROM bench_accel
        WHERE bbox && box(point(%s, %s), point(%s, %s))
          AND pre > %s AND post < %s
    """, (pre_v + 1, INT_MIN, INT_MAX, post_v - 1, pre_v, post_v))
    return cur.fetchall()


def accel_sibling(cur, pre_v, parent_v, direction):
    op = '>' if direction == 'following' else '<'
    cur.execute(f"""
        SELECT pre FROM bench_accel
        WHERE parent = %s AND pre {op} %s
    """, (parent_v, pre_v))
    return cur.fetchall()


# ---------------------------------------------------------------------------
# C. XPath Accelerator (Phase 3, verkleinertes Fenster, gleicher R-Baum)
#
# Die Fensterverkleinerung (Folie 25ff) betrifft ausschliesslich die
# descendant-Achse: pre(v) < pre(n) < post(v) bei der gewaehlten
# Pre-/Post-Kodierung (ein gemeinsamer Zaehler) impliziert bereits
# post(n) < post(v), die zweite Bedingung ist redundant. Fuer ancestor und
# die Sibling-Achsen gibt es keine analoge Verkleinerung (siehe
# Phase3-Verkleinern des Fensters / report_template_task3_phase3.tex), daher
# verwenden ancestor/sibling in Repraesentation C dieselbe Anfrage wie B.
# ---------------------------------------------------------------------------

def accel_descendant_window(cur, pre_v, post_v, height_t):
    pre_upper = post_v + height_t
    post_lower = pre_v - height_t
    cur.execute("""
        SELECT pre FROM bench_accel
        WHERE bbox && box(point(%s, %s), point(%s, %s))
          AND pre > %s AND pre <= %s
          AND post < %s AND post >= %s
    """, (pre_v + 1, post_lower, pre_upper, post_v - 1,
          pre_v, pre_upper, post_v, post_lower))
    return cur.fetchall()


# ---------------------------------------------------------------------------
# D. 1D-Accelerator (Phase 3, nur descendant, geclusterter B+-Baum)
# ---------------------------------------------------------------------------

def accel1d_descendant(cur, pre_v, post_v):
    cur.execute("""
        SELECT pre FROM bench_accel1d
        WHERE pre > %s AND pre < %s
    """, (pre_v, post_v))
    return cur.fetchall()


# ---------------------------------------------------------------------------
# Zeitmessung
# ---------------------------------------------------------------------------

def time_calls(cur, fn, args_list, warmup=3):
    for args in args_list[:warmup]:
        fn(cur, *args)
    elapsed = []
    sizes = []
    for args in args_list:
        start = time.perf_counter()
        rows = fn(cur, *args)
        elapsed.append(time.perf_counter() - start)
        sizes.append(len(rows))
    n = len(elapsed)
    return {
        'mean_ms': 1000 * sum(elapsed) / n if n else 0.0,
        'mean_result_size': sum(sizes) / n if n else 0.0,
        'num_samples': n,
    }


def run_benchmark_for_size(conn, size_label, num_records, height_t, num_samples, seed):
    samples = sample_context_nodes(conn, num_samples, seed)
    records = []

    with conn.cursor() as cur:
        # ancestor
        records.append(dict(size=size_label, num_records=num_records, axis='ancestor',
                             representation='A_EDGE',
                             **time_calls(cur, lambda c, pre, post, parent: edge_ancestor(c, pre),
                                          samples['ancestor'])))
        records.append(dict(size=size_label, num_records=num_records, axis='ancestor',
                             representation='B_Accel_FullWindow',
                             **time_calls(cur, lambda c, pre, post, parent: accel_ancestor_full(c, pre, post),
                                          samples['ancestor'])))
        # Hinweis: die Fensterverkleinerung aus Phase 3 betrifft nur die
        # descendant-Achse (siehe Kommentar bei accel_descendant_window), es
        # gibt daher keine eigene 'C'-Variante fuer ancestor.

        # descendant
        records.append(dict(size=size_label, num_records=num_records, axis='descendant',
                             representation='A_EDGE',
                             **time_calls(cur, lambda c, pre, post, parent: edge_descendant(c, pre),
                                          samples['descendant'])))
        records.append(dict(size=size_label, num_records=num_records, axis='descendant',
                             representation='B_Accel_FullWindow',
                             **time_calls(cur, lambda c, pre, post, parent: accel_descendant_full(c, pre, post),
                                          samples['descendant'])))
        records.append(dict(size=size_label, num_records=num_records, axis='descendant',
                             representation='C_Accel_SmallWindow',
                             **time_calls(cur, lambda c, pre, post, parent: accel_descendant_window(c, pre, post, height_t),
                                          samples['descendant'])))
        records.append(dict(size=size_label, num_records=num_records, axis='descendant',
                             representation='D_Accel1D_Clustered',
                             **time_calls(cur, lambda c, pre, post, parent: accel1d_descendant(c, pre, post),
                                          samples['descendant'])))

        # following/preceding sibling (Richtung steckt in samples['sibling'])
        records.append(dict(size=size_label, num_records=num_records, axis='sibling',
                             representation='A_EDGE',
                             **time_calls(cur, lambda c, pre, post, parent, direction: edge_sibling(c, pre, parent, direction),
                                          samples['sibling'])))
        records.append(dict(size=size_label, num_records=num_records, axis='sibling',
                             representation='B_Accel_FullWindow',
                             **time_calls(cur, lambda c, pre, post, parent, direction: accel_sibling(c, pre, parent, direction),
                                          samples['sibling'])))

    return records


# ---------------------------------------------------------------------------
# Plot (matplotlib, Fallback auf reines Textprotokoll wenn nicht vorhanden)
# ---------------------------------------------------------------------------

def plot_results(records, output_dir):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib nicht verfuegbar, ueberspringe Plots.")
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    axes = sorted({r['axis'] for r in records})

    for axis in axes:
        subset = [r for r in records if r['axis'] == axis]
        representations = sorted({r['representation'] for r in subset})

        plt.figure(figsize=(8, 5))
        for representation in representations:
            series = sorted(
                [r for r in subset if r['representation'] == representation],
                key=lambda r: r['num_records'],
            )
            if not series:
                continue
            xs = [r['num_records'] for r in series]
            ys = [r['mean_ms'] for r in series]
            plt.plot(xs, ys, marker='o', label=representation)

        plt.xlabel('Anzahl Datensaetze (Publikationen)')
        plt.ylabel('mittlere Anfragezeit (ms)')
        plt.title(f'Benchmark: {axis}-Achse')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        path = output_dir / f'benchmark_{axis}.png'
        plt.savefig(path)
        plt.close()
        paths.append(path)

    return paths


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    benchmark_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('../data/benchmark')
    num_samples = int(sys.argv[2]) if len(sys.argv) > 2 else 20

    size_files = sorted(benchmark_dir.glob('bench_size*.xml'),
                        key=lambda p: int(''.join(filter(str.isdigit, p.stem))))
    if not size_files:
        print(f'FEHLER: keine bench_size*.xml in {benchmark_dir} gefunden. '
              f'Zuerst Phase3_Benchmark_Extract.py ausfuehren.')
        sys.exit(1)

    all_records = []
    conn = psycopg2.connect(**db_config)
    try:
        for size_file in size_files:
            size_label = size_file.stem.replace('bench_', '')
            print(f'\n=== Stufe {size_label}: {size_file} ===')

            print('  Baue EDGE-Baum auf ...')
            edge_root = build_edge_root(size_file)
            height_t = tree_height(edge_root)

            accel_rows, content_rows, attribute_rows = [], [], []
            annotate_xml(edge_root, 1, accel_rows, content_rows, attribute_rows)
            num_records = sum(1 for _, _, _, kind, name in accel_rows
                               if kind == 'element' and name in ('article', 'inproceedings'))
            print(f'  {len(accel_rows)} Knoten, {num_records} Publikationen, Baumhoehe={height_t}')

            print('  Lege Schema an und importiere ...')
            setup_schema(conn)
            load_dataset(conn, accel_rows, content_rows, attribute_rows)
            build_indexes(conn)

            print('  Fuehre Benchmark-Anfragen aus ...')
            records = run_benchmark_for_size(conn, size_label, num_records, height_t, num_samples, seed=42)
            all_records.extend(records)

            for r in records:
                print(f"    {r['axis']:10s} {r['representation']:22s} "
                      f"{r['mean_ms']:8.3f} ms  (n={r['num_samples']}, "
                      f"avg_result_size={r['mean_result_size']:.1f})")
    finally:
        conn.close()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = RESULTS_DIR / 'phase3_benchmark.json'
    with json_path.open('w', encoding='utf-8') as handle:
        json.dump(all_records, handle, indent=2)
    print(f'\nErgebnisse gespeichert: {json_path}')

    plot_paths = plot_results(all_records, RESULTS_DIR)
    for path in plot_paths:
        print(f'Plot: {path}')


if __name__ == '__main__':
    main()
