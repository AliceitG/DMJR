#UDF: dotproduct zweier Arrays

import psycopg2

conn = psycopg2.connect(
    dbname="toydb",
    user="postgres",
    password="wortpasst",
    host="localhost"
)

cur = conn.cursor()

# 3. SQL ausführen
cur.execute("""
    CREATE OR REPLACE FUNCTION dotproduct(a DOUBLE PRECISION[], b DOUBLE PRECISION[])
    RETURNS DOUBLE PRECISION AS $$
    DECLARE
        result DOUBLE PRECISION := 0.0;
    BEGIN
        FOR i IN 1..array_length(a, 1) LOOP
            result := result + a[i] * b[i];
        END LOOP;
        RETURN result;
    END;
    $$ LANGUAGE plpgsql IMMUTABLE STRICT;
""")

conn.commit()
cur.close()
conn.close()

