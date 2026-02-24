from src.cli import _sanitize_stem, build_parser


def test_cli_parser_defaults():
    parser = build_parser()
    args = parser.parse_args(["--input", "sample.xlsx"])

    assert args.input == "sample.xlsx"
    assert args.input_dir is None
    assert args.env is None
    assert args.pattern == "*.xlsx"
    assert args.recursive is False
    assert args.fail_fast is False
    assert args.output_dir is None
    assert args.target_acos == 0.30
    assert args.min_bid == 0.10
    assert args.max_bid == 5.00
    assert args.disable_48hr_rule is False
    assert args.skip_nlp is False


def test_cli_parser_input_dir_mode():
    parser = build_parser()
    args = parser.parse_args(["--env", "dev", "--input-dir", "data/samples", "--pattern", "*bulk*.xlsx", "--recursive"])

    assert args.input is None
    assert args.env == "dev"
    assert args.input_dir == "data/samples"
    assert args.pattern == "*bulk*.xlsx"
    assert args.recursive is True


def test_sanitize_stem_removes_problem_characters():
    assert _sanitize_stem("My File (v1)") == "My_File_v1"
