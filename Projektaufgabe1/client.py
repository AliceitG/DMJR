import argparse

from psycopg2 import sql

from api_layer import compare_explain_plans, create_api_functions, fetch_query_ii_sample
from benchmarking import benchmark_final_optimizations, benchmark_matrix
from common import (
    DEFAULT_BENCHMARK_ATTRIBUTES,
    DEFAULT_BENCHMARK_SIZES,
    DEFAULT_BENCHMARK_SPARSITIES,
)
from db_utils import connect_db, print_relation
from generator import generate
from operators import (
    analyze_dataset,
    create_horizontal_indexes,
    create_v2h_view,
    create_vertical_indexes,
    ensure_vertical_layout,
    h2v_general,
    measure_storage,
    test_general_operator_correctness,
)
from toy import setup_toy_example, test_toy_correctness


def phase1_demo():
    setup_toy_example()
    print_relation("h_toy")
    print_relation("v_toy")
    print_relation("v_toy_str")
    print_relation("v_toy_int")
    print_relation("v_toy_all")
    print_relation("h2v_toy")
    test_toy_correctness()

    generate("h_phase1", num_tuples=2000, sparsity=0.75, num_attributes=6)
    print_relation("h_phase1", limit=10)
    print_relation("h_phase1_null_stats")
    print_relation("h_phase1_value_frequency")
    print_relation("h_phase1_generator_audit")


def phase2_demo():
    setup_toy_example()
    h2v_general("h_toy")
    create_v2h_view("h_toy")
    test_general_operator_correctness("h_toy", reference_vertical_view="v_toy_all")

    generate("h_phase2", num_tuples=4000, sparsity=0.875, num_attributes=8)
    h2v_general("h_phase2")
    create_v2h_view("h_phase2")
    create_horizontal_indexes("h_phase2")
    create_vertical_indexes("h_phase2", mode="basic")
    analyze_dataset("h_phase2")
    storage = measure_storage("h_phase2")
    print("\nStorage report:", storage)

    from benchmarking import benchmark_representation

    print(benchmark_representation("h_phase2", "H", duration_s=0.5))
    print(benchmark_representation("h_phase2", "V_VIEW", duration_s=0.5))


def phase3_demo():
    generate("h_phase3", num_tuples=4000, sparsity=0.875, num_attributes=8)
    h2v_general("h_phase3")
    create_v2h_view("h_phase3")
    create_horizontal_indexes("h_phase3")
    create_vertical_indexes("h_phase3", mode="basic")
    create_api_functions("h_phase3")
    analyze_dataset("h_phase3")
    compare_explain_plans("h_phase3")

    from benchmarking import benchmark_representation

    print(benchmark_representation("h_phase3", "V_VIEW", duration_s=0.5))
    print(benchmark_representation("h_phase3", "V_API", duration_s=0.5))
    benchmark_final_optimizations(
        table_name="h_phase3_opt",
        num_tuples=4000,
        sparsity=0.875,
        num_attributes=8,
        duration_s=0.5,
    )


def quick_check():
    setup_toy_example()
    toy_ok = test_toy_correctness()

    h2v_general("h_toy")
    create_v2h_view("h_toy")
    generic_toy_ok = test_general_operator_correctness("h_toy", reference_vertical_view="v_toy_all")

    generate("h_check", num_tuples=2000, sparsity=0.75, num_attributes=6)
    h2v_general("h_check")
    create_v2h_view("h_check")
    create_horizontal_indexes("h_check")
    create_vertical_indexes("h_check", mode="basic")
    create_api_functions("h_check")
    analyze_dataset("h_check")

    generated_ok = test_general_operator_correctness("h_check")

    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM h_check WHERE oid = 1;")
            expected_q_i = cur.fetchone()

            cur.execute("SELECT * FROM q_i(%s);", (1,))
            actual_q_i = cur.fetchone()

            spec, value = fetch_query_ii_sample(cur, "h_check")
            horizontal_q_ii_sql = sql.SQL("SELECT oid FROM {} WHERE {} = %s ORDER BY oid;").format(
                sql.Identifier("h_check"),
                sql.Identifier(spec.name),
            )
            cur.execute(horizontal_q_ii_sql, (value,))
            expected_q_ii = cur.fetchall()

            api_q_ii_sql = (
                "SELECT * FROM q_ii(%s::text, %s::text) ORDER BY oid;"
                if spec.fragment_kind == "str"
                else "SELECT * FROM q_ii(%s::text, %s::integer) ORDER BY oid;"
            )
            cur.execute(api_q_ii_sql, (spec.name, value))
            actual_q_ii = cur.fetchall()

    api_ok = expected_q_i == actual_q_i and expected_q_ii == actual_q_ii

    print("\nQuick check summary")
    print(f"Toy V2H correctness: {toy_ok}")
    print(f"General toy H2V/V2H correctness: {generic_toy_ok}")
    print(f"Generated dataset H2V/V2H correctness: {generated_ok}")
    print(f"API correctness: {api_ok}")

    return toy_ok and generic_toy_ok and generated_ok and api_ok


def build_parser():
    parser = argparse.ArgumentParser(description="Project client for sparse e-commerce data.")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("toy", help="Create the toy example.")
    subparsers.add_parser("phase1-demo", help="Run a short Phase 1 demo.")
    subparsers.add_parser("phase2-demo", help="Run a short Phase 2 demo.")
    subparsers.add_parser("phase3-demo", help="Run a short Phase 3 demo.")
    subparsers.add_parser("quick-check", help="Run a compact end-to-end correctness check.")

    generate_parser = subparsers.add_parser("generate", help="Generate a horizontal benchmark table.")
    generate_parser.add_argument("--table", default="h_generated")
    generate_parser.add_argument("--num-tuples", type=int, default=2000)
    generate_parser.add_argument("--sparsity", type=float, default=0.75)
    generate_parser.add_argument("--num-attributes", type=int, default=6)
    generate_parser.add_argument("--seed", type=int, default=42)

    h2v_parser = subparsers.add_parser("h2v", help="Run H2V for a table.")
    h2v_parser.add_argument("--table", required=True)

    v2h_parser = subparsers.add_parser("v2h", help="Create the V2H view for a table.")
    v2h_parser.add_argument("--table", required=True)

    api_parser = subparsers.add_parser("api", help="Create DB API functions q_i and q_ii.")
    api_parser.add_argument("--table", required=True)

    explain_parser = subparsers.add_parser("compare-plans", help="Compare EXPLAIN ANALYZE for view vs API.")
    explain_parser.add_argument("--table", required=True)
    explain_parser.add_argument("--oid", type=int, default=1)
    explain_parser.add_argument("--attribute")

    benchmark_parser = subparsers.add_parser("benchmark", help="Run the Phase 2/3 benchmark matrix.")
    benchmark_parser.add_argument("--table", default="h_benchmark")
    benchmark_parser.add_argument("--sizes", nargs="+", type=int, default=DEFAULT_BENCHMARK_SIZES)
    benchmark_parser.add_argument("--attributes", nargs="+", type=int, default=DEFAULT_BENCHMARK_ATTRIBUTES)
    benchmark_parser.add_argument("--sparsities", nargs="+", type=float, default=DEFAULT_BENCHMARK_SPARSITIES)
    benchmark_parser.add_argument("--duration", type=float, default=1.0)
    benchmark_parser.add_argument("--include-api", action="store_true")
    benchmark_parser.add_argument("--vertical-index-mode", default="basic", choices=["basic", "covering", "partial"])

    final_opt_parser = subparsers.add_parser(
        "final-opt", help="Benchmark at least two additional vertical optimizations."
    )
    final_opt_parser.add_argument("--table", default="h_optim")
    final_opt_parser.add_argument("--num-tuples", type=int, default=8000)
    final_opt_parser.add_argument("--sparsity", type=float, default=0.875)
    final_opt_parser.add_argument("--num-attributes", type=int, default=10)
    final_opt_parser.add_argument("--duration", type=float, default=1.0)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command in {None, "quick-check"}:
        quick_check()
    elif args.command == "toy":
        setup_toy_example()
    elif args.command == "phase1-demo":
        phase1_demo()
    elif args.command == "phase2-demo":
        phase2_demo()
    elif args.command == "phase3-demo":
        phase3_demo()
    elif args.command == "generate":
        generate(
            table_name=args.table,
            num_tuples=args.num_tuples,
            sparsity=args.sparsity,
            num_attributes=args.num_attributes,
            seed=args.seed,
        )
    elif args.command == "h2v":
        h2v_general(args.table)
    elif args.command == "v2h":
        ensure_vertical_layout(args.table, require_view=True)
    elif args.command == "api":
        create_api_functions(args.table)
    elif args.command == "compare-plans":
        compare_explain_plans(args.table, sample_oid=args.oid, sample_attribute=args.attribute)
    elif args.command == "benchmark":
        benchmark_matrix(
            table_name=args.table,
            sizes=args.sizes,
            attribute_counts=args.attributes,
            sparsities=args.sparsities,
            duration_s=args.duration,
            include_api=args.include_api,
            vertical_index_mode=args.vertical_index_mode,
        )
    elif args.command == "final-opt":
        benchmark_final_optimizations(
            table_name=args.table,
            num_tuples=args.num_tuples,
            sparsity=args.sparsity,
            num_attributes=args.num_attributes,
            duration_s=args.duration,
        )
    else:
        parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
