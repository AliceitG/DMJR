import hashlib
from dataclasses import dataclass
from pathlib import Path

from psycopg2 import sql


MAX_ATTRIBUTES = 24
DEFAULT_VALUE_FREQUENCY = 5
DEFAULT_BENCHMARK_SIZES = [2000, 4000, 8000]
DEFAULT_BENCHMARK_ATTRIBUTES = [5, 10, 15]
DEFAULT_BENCHMARK_SPARSITIES = [0.75, 0.875, 0.9375]
RESULTS_DIR = Path(__file__).resolve().parent / "results"


@dataclass(frozen=True)
class AttributeSpec:
    name: str
    sql_type: str
    fragment_kind: str


def make_object_name(*parts):
    raw = "_".join(str(part) for part in parts if part)
    if len(raw) <= 63:
        return raw

    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    return f"{raw[:54]}_{digest}"


def dataset_object_names(table_name):
    return {
        "oids": f"{table_name}_oids",
        "v_str": f"{table_name}_v_str",
        "v_int": f"{table_name}_v_int",
        "v_all": f"{table_name}_v_all",
        "view": f"{table_name}_view",
        "null_stats": f"{table_name}_null_stats",
        "value_frequency": f"{table_name}_value_frequency",
        "generator_audit": f"{table_name}_generator_audit",
    }


def quoted_identifier(conn, name):
    return sql.Identifier(name).as_string(conn)


def quoted_literal(conn, value):
    return sql.Literal(value).as_string(conn)


def ensure_results_dir():
    RESULTS_DIR.mkdir(exist_ok=True)
    return RESULTS_DIR


def classify_type(sql_type):
    normalized = sql_type.lower()
    if (
        normalized == "text"
        or normalized.startswith("character varying")
        or normalized.startswith("character")
        or normalized.startswith("varchar")
    ):
        return "str"
    if normalized in {"smallint", "integer", "bigint", "int2", "int4", "int8"}:
        return "int"
    raise ValueError(f"Unsupported SQL type '{sql_type}'.")
