DROP TABLE IF EXISTS edge;
DROP TABLE IF EXISTS node;

CREATE TABLE node (
    id      SERIAL PRIMARY KEY,
    s_id    VARCHAR,
    type    VARCHAR NOT NULL,
    content TEXT
);

CREATE TABLE edge (
    "from"  INTEGER NOT NULL REFERENCES node(id),
    "to"    INTEGER NOT NULL REFERENCES node(id),
    PRIMARY KEY ("from", "to")
);
