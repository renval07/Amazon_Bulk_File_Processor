from src.settings import get_runtime_profile_name, load_runtime_profile


def test_runtime_profile_name_defaults_to_local():
    assert get_runtime_profile_name("unknown") == "local"
    assert get_runtime_profile_name("prod") == "prod"


def test_load_runtime_profile_has_required_fields():
    profile = load_runtime_profile("dev")
    assert profile["name"] == "dev"
    assert "default_output_dir" in profile
    assert "run_history_path" in profile
    assert "ui" in profile
