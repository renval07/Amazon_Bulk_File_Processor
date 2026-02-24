from src.cli import _sanitize_stem, build_parser


def test_cli_parser_defaults():
    parser = build_parser()
    args = parser.parse_args(["--input", "sample.xlsx"])

    assert args.output_dir == "outputs"
    assert args.target_acos == 0.30
    assert args.min_bid == 0.10
    assert args.max_bid == 5.00
    assert args.disable_48hr_rule is False
    assert args.skip_nlp is False


def test_sanitize_stem_removes_problem_characters():
    assert _sanitize_stem("My File (v1)") == "My_File_v1"
