import csv
import json
import random
import time

from psycopg2 import sql

from api_layer import create_api_functions
from common import (
    DEFAULT_BENCHMARK_ATTRIBUTES,
    DEFAULT_BENCHMARK_SIZES,
    DEFAULT_BENCHMARK_SPARSITIES,
    RESULTS_DIR,
    ensure_results_dir,
)
from db_utils import connect_db
from generator import generate
from operators import (
    analyze_dataset,
    create_horizontal_indexes,
    create_v2h_view,
    create_vertical_indexes,
    drop_vertical_indexes,
    h2v_general,
    measure_storage,
    prepare_query_ii_samples,
)


def run_timed_query_loop(cur, query_factory, duration_s, warmup=25):
    for _ in range(warmup):
        statement, params = query_factory()
        cur.execute(statement, params)
        cur.fetchall()

    start = time.perf_counter()
    count = 0
    while time.perf_counter() - start < duration_s:
        statement, params = query_factory()
        cur.execute(statement, params)
        cur.fetchall()
        count += 1

    elapsed = time.perf_counter() - start
    qps = count / elapsed if elapsed > 0 else 0.0
    return {
        "count": count,
        "elapsed_s": round(elapsed, 4),
        "qps": round(qps, 4),
    }


def benchmark_representation(horizontal_table, representation, duration_s=1.0, seed=42):
    if representation not in {"H", "V_VIEW", "V_API"}:
        raise ValueError("representation must be one of: H, V_VIEW, V_API.")

    from common import dataset_object_names

    names = dataset_object_names(horizontal_table)
    rng = random.Random(seed)

    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT MAX(oid) FROM {};").format(sql.Identifier(horizontal_table)))
            max_oid = cur.fetchone()[0]
            if max_oid is None:
                raise RuntimeError(f"Table '{horizontal_table}' is empty.")

            eligible_specs, domains = prepare_query_ii_samples(cur, horizontal_table)

            if representation == "H":
                relation_name = horizontal_table
                q_i_sql = sql.SQL("SELECT * FROM {} WHERE oid = %s;").format(
                    sql.Identifier(relation_name)
                ).as_string(conn)
                q_ii_sql = {
                    spec.name: sql.SQL("SELECT oid FROM {} WHERE {} = %s;").format(
                        sql.Identifier(relation_name),
                        sql.Identifier(spec.name),
                    ).as_string(conn)
                    for spec in eligible_specs
                }
            elif representation == "V_VIEW":
                relation_name = names["view"]
                q_i_sql = sql.SQL("SELECT * FROM {} WHERE oid = %s;").format(
                    sql.Identifier(relation_name)
                ).as_string(conn)
                q_ii_sql = {
                    spec.name: sql.SQL("SELECT oid FROM {} WHERE {} = %s;").format(
                        sql.Identifier(relation_name),
                        sql.Identifier(spec.name),
                    ).as_string(conn)
                    for spec in eligible_specs
                }
            else:
                q_i_sql = "SELECT * FROM q_i(%s);"
                q_ii_sql = {
                    spec.name: (
                        "SELECT * FROM q_ii(%s::text, %s::text);"
                        if spec.fragment_kind == "str"
                        else "SELECT * FROM q_ii(%s::text, %s::integer);"
                    )
                    for spec in eligible_specs
                }

            def query_i_factory():
                return q_i_sql, (rng.randint(1, max_oid),)

            def query_ii_factory():
                spec = rng.choice(eligible_specs)
                value = rng.choice(domains[spec.name])
                if representation == "V_API":
                    return q_ii_sql[spec.name], (spec.name, value)
                return q_ii_sql[spec.name], (value,)

            query_i_result = run_timed_query_loop(cur, query_i_factory, duration_s)
            query_ii_result = run_timed_query_loop(cur, query_ii_factory, duration_s)

    return {
        "representation": representation,
        "query_i_qps": query_i_result["qps"],
        "query_i_count": query_i_result["count"],
        "query_i_elapsed_s": query_i_result["elapsed_s"],
        "query_ii_qps": query_ii_result["qps"],
        "query_ii_count": query_ii_result["count"],
        "query_ii_elapsed_s": query_ii_result["elapsed_s"],
    }


def save_records(prefix, records):
    ensure_results_dir()
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    json_path = RESULTS_DIR / f"{prefix}_{timestamp}.json"
    csv_path = RESULTS_DIR / f"{prefix}_{timestamp}.csv"

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(records, handle, indent=2)

    if records:
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0].keys()))
            writer.writeheader()
            writer.writerows(records)

    return json_path, csv_path


def write_svg_line_chart(output_path, title, series_data, x_label, y_label):
    width = 960
    height = 560
    margin_left = 90
    margin_right = 260
    margin_top = 60
    margin_bottom = 70
    palette = ["#0f766e", "#dc2626", "#2563eb", "#ca8a04", "#7c3aed", "#ea580c", "#0891b2", "#4f46e5"]

    all_points = [point for series in series_data for point in series["points"]]
    if not all_points:
        return None

    xs = [point[0] for point in all_points]
    ys = [point[1] for point in all_points]
    x_min = min(xs)
    x_max = max(xs)
    y_min = 0.0
    y_max = max(ys)

    if x_min == x_max:
        x_max += 1
    if y_max <= y_min:
        y_max = y_min + 1

    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom

    def map_x(value):
        return margin_left + ((value - x_min) / (x_max - x_min)) * plot_width

    def map_y(value):
        return margin_top + plot_height - ((value - y_min) / (y_max - y_min)) * plot_height

    svg_lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white" />',
        f'<text x="{width / 2}" y="32" text-anchor="middle" font-size="22" font-family="Helvetica, Arial, sans-serif">{title}</text>',
        f'<line x1="{margin_left}" y1="{margin_top + plot_height}" x2="{margin_left + plot_width}" y2="{margin_top + plot_height}" stroke="#111827" stroke-width="2"/>',
        f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_height}" stroke="#111827" stroke-width="2"/>',
        f'<text x="{margin_left + plot_width / 2}" y="{height - 20}" text-anchor="middle" font-size="14" font-family="Helvetica, Arial, sans-serif">{x_label}</text>',
        f'<text x="24" y="{margin_top + plot_height / 2}" transform="rotate(-90 24 {margin_top + plot_height / 2})" text-anchor="middle" font-size="14" font-family="Helvetica, Arial, sans-serif">{y_label}</text>',
    ]

    unique_xs = sorted(set(xs))
    for x_value in unique_xs:
        x_pos = map_x(x_value)
        svg_lines.append(
            f'<line x1="{x_pos}" y1="{margin_top}" x2="{x_pos}" y2="{margin_top + plot_height}" stroke="#e5e7eb" stroke-width="1"/>'
        )
        svg_lines.append(
            f'<text x="{x_pos}" y="{margin_top + plot_height + 24}" text-anchor="middle" font-size="12" font-family="Helvetica, Arial, sans-serif">{x_value}</text>'
        )

    for step in range(6):
        y_value = y_min + ((y_max - y_min) * step / 5)
        y_pos = map_y(y_value)
        svg_lines.append(
            f'<line x1="{margin_left}" y1="{y_pos}" x2="{margin_left + plot_width}" y2="{y_pos}" stroke="#e5e7eb" stroke-width="1"/>'
        )
        svg_lines.append(
            f'<text x="{margin_left - 12}" y="{y_pos + 4}" text-anchor="end" font-size="12" font-family="Helvetica, Arial, sans-serif">{y_value:.1f}</text>'
        )

    legend_y = margin_top + 10
    for index, series in enumerate(series_data):
        color = palette[index % len(palette)]
        points = series["points"]
        polyline_points = " ".join(f"{map_x(x):.2f},{map_y(y):.2f}" for x, y in points)
        svg_lines.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="3" points="{polyline_points}" />'
        )
        for x_value, y_value in points:
            svg_lines.append(
                f'<circle cx="{map_x(x_value):.2f}" cy="{map_y(y_value):.2f}" r="4" fill="{color}" />'
            )

        legend_x = width - margin_right + 24
        svg_lines.append(
            f'<line x1="{legend_x}" y1="{legend_y}" x2="{legend_x + 28}" y2="{legend_y}" stroke="{color}" stroke-width="4" />'
        )
        svg_lines.append(
            f'<text x="{legend_x + 36}" y="{legend_y + 4}" font-size="12" font-family="Helvetica, Arial, sans-serif">{series["label"]}</text>'
        )
        legend_y += 22

    svg_lines.append("</svg>")

    output_path.write_text("\n".join(svg_lines), encoding="utf-8")
    return output_path


def render_svg_benchmark_plots(records, prefix):
    ensure_results_dir()
    output_paths = []
    attribute_counts = sorted({record["num_attributes"] for record in records})
    metrics = ["query_i_qps", "query_ii_qps"]

    for metric in metrics:
        for attribute_count in attribute_counts:
            subset = [record for record in records if record["num_attributes"] == attribute_count]
            if not subset:
                continue

            representations = sorted({record["representation"] for record in subset})
            sparsities = sorted({record["sparsity"] for record in subset})
            series_data = []

            for representation in representations:
                for sparsity in sparsities:
                    series_records = sorted(
                        [
                            record
                            for record in subset
                            if record["representation"] == representation and record["sparsity"] == sparsity
                        ],
                        key=lambda record: record["num_tuples"],
                    )
                    if not series_records:
                        continue

                    series_data.append(
                        {
                            "label": f"{representation}, s={sparsity}",
                            "points": [
                                (record["num_tuples"], record[metric]) for record in series_records
                            ],
                        }
                    )

            output_path = RESULTS_DIR / f"{prefix}_{metric}_a{attribute_count}.svg"
            created_path = write_svg_line_chart(
                output_path=output_path,
                title=f"{metric} for num_attributes={attribute_count}",
                series_data=series_data,
                x_label="num_tuples",
                y_label=metric,
            )
            if created_path is not None:
                output_paths.append(created_path)

    return output_paths


def plot_benchmark_results(records, prefix):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib is not installed. Falling back to SVG plot generation.")
        return render_svg_benchmark_plots(records, prefix)

    ensure_results_dir()
    output_paths = []
    attribute_counts = sorted({record["num_attributes"] for record in records})
    metrics = ["query_i_qps", "query_ii_qps"]

    for metric in metrics:
        for attribute_count in attribute_counts:
            subset = [record for record in records if record["num_attributes"] == attribute_count]
            if not subset:
                continue

            plt.figure(figsize=(10, 6))
            representations = sorted({record["representation"] for record in subset})
            sparsities = sorted({record["sparsity"] for record in subset})

            for representation in representations:
                for sparsity in sparsities:
                    series = sorted(
                        [
                            record
                            for record in subset
                            if record["representation"] == representation and record["sparsity"] == sparsity
                        ],
                        key=lambda record: record["num_tuples"],
                    )
                    if not series:
                        continue

                    xs = [record["num_tuples"] for record in series]
                    ys = [record[metric] for record in series]
                    label = f"{representation}, s={sparsity}"
                    plt.plot(xs, ys, marker="o", label=label)

            plt.xlabel("num_tuples")
            plt.ylabel(metric)
            plt.title(f"{metric} for num_attributes={attribute_count}")
            plt.grid(True, alpha=0.3)
            plt.legend()

            output_path = RESULTS_DIR / f"{prefix}_{metric}_a{attribute_count}.png"
            plt.tight_layout()
            plt.savefig(output_path)
            plt.close()
            output_paths.append(output_path)

    return output_paths


def benchmark_matrix(
    table_name="h_benchmark",
    sizes=None,
    attribute_counts=None,
    sparsities=None,
    duration_s=1.0,
    include_api=False,
    vertical_index_mode="basic",
    seed=42,
):
    sizes = sizes or DEFAULT_BENCHMARK_SIZES
    attribute_counts = attribute_counts or DEFAULT_BENCHMARK_ATTRIBUTES
    sparsities = sparsities or DEFAULT_BENCHMARK_SPARSITIES

    records = []

    for num_tuples in sizes:
        for num_attributes in attribute_counts:
            for sparsity in sparsities:
                print(
                    f"\nBenchmark setup: |H|={num_tuples}, |A|={num_attributes}, sparsity={sparsity}"
                )
                generate(
                    table_name=table_name,
                    num_tuples=num_tuples,
                    sparsity=sparsity,
                    num_attributes=num_attributes,
                    seed=seed,
                )
                create_horizontal_indexes(table_name)
                h2v_general(table_name)
                create_v2h_view(table_name)
                drop_vertical_indexes(table_name)
                create_vertical_indexes(table_name, mode=vertical_index_mode)
                analyze_dataset(table_name)

                storage = measure_storage(table_name)
                measurements = [
                    benchmark_representation(table_name, "H", duration_s=duration_s, seed=seed),
                    benchmark_representation(table_name, "V_VIEW", duration_s=duration_s, seed=seed),
                ]

                if include_api:
                    create_api_functions(table_name)
                    analyze_dataset(table_name)
                    measurements.append(
                        benchmark_representation(table_name, "V_API", duration_s=duration_s, seed=seed)
                    )

                for measurement in measurements:
                    record = {
                        "table_name": table_name,
                        "num_tuples": num_tuples,
                        "num_attributes": num_attributes,
                        "sparsity": sparsity,
                        "duration_s": duration_s,
                        "representation": measurement["representation"],
                        "index_mode": vertical_index_mode,
                        "query_i_qps": measurement["query_i_qps"],
                        "query_i_count": measurement["query_i_count"],
                        "query_i_elapsed_s": measurement["query_i_elapsed_s"],
                        "query_ii_qps": measurement["query_ii_qps"],
                        "query_ii_count": measurement["query_ii_count"],
                        "query_ii_elapsed_s": measurement["query_ii_elapsed_s"],
                        "horizontal_mb": storage["horizontal_mb"],
                        "vertical_mb": storage["vertical_mb"],
                        "storage_mb": storage["horizontal_mb"]
                        if measurement["representation"] == "H"
                        else storage["vertical_mb"],
                    }
                    records.append(record)

    prefix = "phase3_benchmark" if include_api else "phase2_benchmark"
    json_path, csv_path = save_records(prefix, records)
    plot_paths = plot_benchmark_results(records, prefix)

    print(f"\nBenchmark records written to {json_path} and {csv_path}.")
    if plot_paths:
        print("Plots:")
        for plot_path in plot_paths:
            print(plot_path)

    return records


def benchmark_final_optimizations(
    table_name="h_optim",
    num_tuples=8000,
    sparsity=0.875,
    num_attributes=10,
    duration_s=1.0,
    seed=42,
):
    generate(
        table_name=table_name,
        num_tuples=num_tuples,
        sparsity=sparsity,
        num_attributes=num_attributes,
        seed=seed,
    )
    h2v_general(table_name)
    create_v2h_view(table_name)

    records = []
    for mode in ["basic", "covering", "partial"]:
        drop_vertical_indexes(table_name)
        create_vertical_indexes(table_name, mode=mode)
        create_api_functions(table_name)
        analyze_dataset(table_name)

        storage = measure_storage(table_name)
        measurement = benchmark_representation(table_name, "V_API", duration_s=duration_s, seed=seed)
        records.append(
            {
                "table_name": table_name,
                "optimization_mode": mode,
                "num_tuples": num_tuples,
                "num_attributes": num_attributes,
                "sparsity": sparsity,
                "duration_s": duration_s,
                "query_i_qps": measurement["query_i_qps"],
                "query_ii_qps": measurement["query_ii_qps"],
                "vertical_mb": storage["vertical_mb"],
            }
        )

    json_path, csv_path = save_records("final_optimizations", records)
    print(f"Final optimization benchmark written to {json_path} and {csv_path}.")
    return records
