postgres=# CREATE TABLE accel (
  pre    INTEGER,
  post   INTEGER,
  parent INTEGER,
  kind   TEXT,
  name   TEXT
);

CREATE TABLE content (
  pre  INTEGER,
  text TEXT
);
CREATE TABLE
CREATE TABLE
postgres=# CREATE TABLE attribute ( pre  INTEGER,
  text TEXT
);

Semantik:
Die Relation accel modelliert die Struktur des EDGE-Modells. 
Sie speichert für jeden Knoten die Vor- und Nachordnungsnummer (pre, post) sowie die hierarchische Einordnung über parent. 
Zusätzlich beschreiben kind den Knotentyp und name die Bezeichnung des Knotens.
Die Relation content enthält den zugehörigen Textinhalt eines Knotens. 
Über das Attribut pre wird jeder Texteintrag eindeutig dem entsprechenden Knoten aus accel zugeordnet. 
Das Attribut text speichert den eigentlichen Inhalt.
Die Relation attribute enthält zusätzliche Attributeigenschaften eines Knotens oder einer Entität. 
Über pre wird der Eintrag dem jeweiligen Knoten zugeordnet, und text speichert den zugehörigen Attributwert bzw. 
die Attributbeschreibung. Damit ergänzt attribute die Struktur- und Inhaltsinformationen aus accel und content.
