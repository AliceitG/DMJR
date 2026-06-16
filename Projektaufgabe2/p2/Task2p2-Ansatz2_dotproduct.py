#UDF: dotproduct zweier Arrays

import psycopg2

conn = psycopg2.connect(
    dbname="toydb",
    user="postgres",
    password="wortpasst",
    host="localhost"
)

cur = conn.cursor()

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



"""
STRICT

    CALLED ON NULL INPUT (the default) indicates that the function will be called normally when some of its arguments are null.
     It is then the function author's responsibility to check for null values if necessary and respond appropriately.

    RETURNS NULL ON NULL INPUT or STRICT indicates that the function always returns null whenever any of its arguments are null.
     If this parameter is specified, the function is not executed when there are null arguments; instead a null result is assumed automatically.

Notes
    If a function is declared STRICT with a VARIADIC argument, the strictness check tests that the variadic array as a whole is non-null.
     The function will still be called if the array has null elements.
     
info 
    https://blog.mclaughlinsoftware.com/2022/04/27/pl-pgsql-array-listing/
"""
