import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import psycopg2

db_config = {
    "dbname": "projektaufgabe1",
    "user": "projektaufgabe1_user",
    "password": "1234",
    "host": "localhost",
}

ALLOWED_FIELDS = {
    'author', 'title', 'pages', 'year', 'volume',
    'journal', 'number', 'ee', 'url', 'booktitle', 'crossref',
}


# ---------------------------------------------------------------------------
# Node class with to_edge_model()
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
        """Insert this node (and all descendants) into the EDGE model tables."""
        cur.execute(
            "INSERT INTO node (s_id, type, content) VALUES (%s, %s, %s) RETURNING id",
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

    def print_tree(self, indent: int = 0) -> None:
        label = f"[{self.type}]"
        if self.s_id:
            label += f" {self.s_id}"
        if self.content:
            label += f": {self.content}"
        print("  " * indent + label)
        for child in self.children:
            child.print_tree(indent + 1)


# ---------------------------------------------------------------------------
# XML parsing helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    return (
        text.replace("&uuml;", "ü").replace("&auml;", "ä").replace("&ouml;", "ö")
            .replace("&Uuml;", "Ü").replace("&Auml;", "Ä").replace("&Ouml;", "Ö")
            .replace("&szlig;", "ß")
    )


def _text_of(elem, tag: str) -> str:
    child = elem.find(tag)
    return (child.text or "").strip() if child is not None and child.text else ""


def _venue(pub) -> str:
    key = pub.attrib.get("key", "").lower()
    booktitle = _text_of(pub, "booktitle").lower()
    journal = _text_of(pub, "journal").lower()
    if "sigmod" in key or "sigmod" in booktitle:
        return "sigmod"
    if "pvldb" in key or "vldb" in journal:
        return "vldb"
    if "icde" in key or "icde" in booktitle:
        return "icde"
    return "unknown"


def _pub_sid(pub) -> str:
    key = pub.attrib.get("key", "")
    return key.split("/")[-1] if key else pub.tag


# ---------------------------------------------------------------------------
# Build in-memory node tree
# ---------------------------------------------------------------------------

def build_node_tree(input_path: Path) -> Node:
    xml_text = _normalize(input_path.read_text(encoding="utf-8"))
    src_root = ET.fromstring(xml_text)

    root = Node("bib", "bib")
    venue_nodes: dict[str, Node] = {}
    year_nodes: dict[tuple, Node] = {}

    for pub in src_root:
        venue = _venue(pub)
        year = _text_of(pub, "year")

        if venue not in venue_nodes:
            venue_nodes[venue] = root.add_child(Node(venue, "venue"))

        key = (venue, year)
        if key not in year_nodes:
            year_nodes[key] = venue_nodes[venue].add_child(
                Node(f"{venue}_{year}", "year")
            )

        pub_node = year_nodes[key].add_child(Node(_pub_sid(pub), pub.tag))

        for child in pub:
            if child.tag in ALLOWED_FIELDS:
                pub_node.add_child(Node(None, child.tag, (child.text or "").strip()))

    return root


# ---------------------------------------------------------------------------
# Database import
# ---------------------------------------------------------------------------

def import_to_db(root: Node) -> None:
    conn = psycopg2.connect(**db_config)
    try:
        with conn:
            with conn.cursor() as cur:
                root.to_edge_model(cur, parent_id=None)
        print("Datenbankimport erfolgreich.")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python phase1_import.py toy_example.txt")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    root = build_node_tree(input_path)

    print("=== EDGE-Modell Toy-Beispiel (Konsolenausgabe) ===")
    root.print_tree()

    print("\n=== Datenbankimport ===")
    try:
        import_to_db(root)
    except Exception as e:
        print(f"Fehler beim DB-Import: {e}")
