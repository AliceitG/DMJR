import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import psycopg2

# Datenbankverbindung – gleiche Konfiguration wie in Projektaufgabe 1
db_config = {
    "dbname": "projektaufgabe1",
    "user": "projektaufgabe1_user",
    "password": "1234",
    "host": "localhost",
}

# Diese XML-Felder werden beim Import berücksichtigt, alle anderen werden ignoriert
# (mdate und orcid werden damit automatisch ausgefiltert)
ALLOWED_FIELDS = {
    'author', 'title', 'pages', 'year', 'volume',
    'journal', 'number', 'ee', 'url', 'booktitle', 'crossref',
}


# ---------------------------------------------------------------------------
# Node-Klasse: repräsentiert einen Knoten im EDGE-Modell-Baum
# ---------------------------------------------------------------------------

class Node:
    def __init__(self, s_id, type_, content=None):
        # s_id: symbolischer Bezeichner, z.B. "vldb", "SchmittKAMM23" (bei Blattknoten None)
        self.s_id = s_id
        # type: Knotentyp, z.B. "venue", "year", "article", "author"
        self.type = type_
        # content: Textinhalt, nur bei Blattknoten gesetzt, z.B. "Daniel Ulrich Schmitt"
        self.content = content
        # children: Liste der Kindknoten (so entsteht der Baum im Speicher)
        self.children: list['Node'] = []
        # db_id: wird nach dem DB-Insert gesetzt (die auto-generierte id aus PostgreSQL)
        self.db_id: int | None = None

    def add_child(self, child: 'Node') -> 'Node':
        # Kindknoten hinzufügen und zurückgeben (für bequemes Chaining)
        self.children.append(child)
        return child

    def to_edge_model(self, cur, parent_id: int | None = None) -> None:
        # Schritt 1: diesen Knoten in die node-Tabelle einfügen
        # RETURNING id liefert die automatisch vergebene id direkt zurück
        cur.execute(
            "INSERT INTO node (s_id, type, content) VALUES (%s, %s, %s) RETURNING id",
            (self.s_id, self.type, self.content),
        )
        self.db_id = cur.fetchone()[0]

        # Schritt 2: Kante zum Elternknoten in die edge-Tabelle einfügen
        # (für den Wurzelknoten "bib" gibt es keinen Elternknoten)
        if parent_id is not None:
            cur.execute(
                'INSERT INTO edge ("from", "to") VALUES (%s, %s)',
                (parent_id, self.db_id),
            )

        # Schritt 3: rekursiv alle Kindknoten einfügen (Tiefensuche / DFS)
        # dadurch werden Knoten in Dokumentreihenfolge eingefügt → id entspricht Position
        for child in self.children:
            child.to_edge_model(cur, self.db_id)

    def print_tree(self, indent: int = 0) -> None:
        # Konsolenausgabe: Einrückung zeigt die Tiefe im Baum
        label = f"[{self.type}]"
        if self.s_id:
            label += f" {self.s_id}"
        if self.content:
            label += f": {self.content}"
        print("  " * indent + label)
        for child in self.children:
            child.print_tree(indent + 1)


# ---------------------------------------------------------------------------
# Hilfsfunktionen für das XML-Parsing
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    # Die DBLP verwendet HTML-Entities für Sonderzeichen (z.B. &uuml; statt ü)
    # ElementTree kennt diese ohne DTD nicht → manuell ersetzen bevor der Parser läuft
    return (
        text.replace("&uuml;", "ü").replace("&auml;", "ä").replace("&ouml;", "ö")
            .replace("&Uuml;", "Ü").replace("&Auml;", "Ä").replace("&Ouml;", "Ö")
            .replace("&szlig;", "ß")
    )


def _text_of(elem, tag: str) -> str:
    # Liest den Textinhalt eines Kindelements aus, z.B. _text_of(pub, "year") → "2023"
    # Gibt "" zurück wenn das Element nicht existiert (kein Fehler)
    child = elem.find(tag)
    return (child.text or "").strip() if child is not None and child.text else ""


def _venue(pub) -> str:
    # Bestimmt die Publikationsvenue anhand des DBLP-Keys und des Titels/Journals
    # Beispiel: key="journals/pvldb/SchmittKAMM23" → "vldb"
    key = pub.attrib.get("key", "").lower()
    booktitle = _text_of(pub, "booktitle").lower()
    journal = _text_of(pub, "journal").lower()
    if "sigmod" in key or "sigmod" in booktitle:
        return "sigmod"
    if "pvldb" in key or "vldb" in journal:
        return "vldb"
    if "icde" in key or "icde" in booktitle:
        return "icde"
    if "pacmmod" in key:
        return "pacmmod"
    return "unknown"


def _pub_sid(pub) -> str:
    # Extrahiert den Publikationsschlüssel aus dem DBLP-Key
    # Beispiel: "journals/pvldb/SchmittKAMM23" → "SchmittKAMM23"
    key = pub.attrib.get("key", "")
    return key.split("/")[-1] if key else pub.tag


# ---------------------------------------------------------------------------
# Baum im Arbeitsspeicher aufbauen
# ---------------------------------------------------------------------------

def build_node_tree(input_path: Path) -> Node:
    # XML-Datei lesen und Sonderzeichen normalisieren
    xml_text = _normalize(input_path.read_text(encoding="utf-8"))
    src_root = ET.fromstring(xml_text)

    # Wurzelknoten "bib"
    root = Node("bib", "bib")

    # Dictionaries um Venue- und Jahr-Knoten wiederzuverwenden
    # (damit nicht für jede Publikation ein neuer vldb-Knoten angelegt wird)
    venue_nodes: dict[str, Node] = {}
    year_nodes: dict[tuple, Node] = {}

    for pub in src_root:
        venue = _venue(pub)           # z.B. "vldb"
        year = _text_of(pub, "year")  # z.B. "2023"

        # Venue-Knoten anlegen falls noch nicht vorhanden (erste Publikation dieser Venue)
        if venue not in venue_nodes:
            venue_nodes[venue] = root.add_child(Node(venue, "venue"))

        # Jahr-Knoten anlegen falls noch nicht vorhanden (erste Publikation dieses Jahres)
        key = (venue, year)
        if key not in year_nodes:
            year_nodes[key] = venue_nodes[venue].add_child(
                Node(f"{venue}_{year}", "year")
            )

        # Publikationsknoten unter den richtigen Jahr-Knoten hängen
        pub_node = year_nodes[key].add_child(Node(_pub_sid(pub), pub.tag))

        # Felder der Publikation als Blattknoten anhängen (nur erlaubte Felder)
        for child in pub:
            if child.tag in ALLOWED_FIELDS:
                pub_node.add_child(Node(None, child.tag, (child.text or "").strip()))

    return root


# ---------------------------------------------------------------------------
# Datenbankimport
# ---------------------------------------------------------------------------

def import_to_db(root: Node) -> None:
    conn = psycopg2.connect(**db_config)
    try:
        with conn:  # automatisches commit/rollback
            with conn.cursor() as cur:
                # Baum ab Wurzel rekursiv in die DB schreiben
                root.to_edge_model(cur, parent_id=None)
        print("Datenbankimport erfolgreich.")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python phase1_import.py toy_example.txt")
        sys.exit(1)

    input_path = Path(sys.argv[1])

    # Schritt 1: XML einlesen und Baum im Speicher aufbauen
    root = build_node_tree(input_path)

    # Schritt 2: Baum auf der Konsole ausgeben (Korrektheitsprüfung)
    print("=== EDGE-Modell Toy-Beispiel (Konsolenausgabe) ===")
    root.print_tree()

    # Schritt 3: Baum in die Datenbank importieren
    print("\n=== Datenbankimport ===")
    try:
        import_to_db(root)
    except Exception as e:
        print(f"Fehler beim DB-Import: {e}")
