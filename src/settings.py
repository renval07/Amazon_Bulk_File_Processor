import json
import os
from pathlib import Path


SUPPORTED_PROFILES = {"local", "dev", "prod"}
DEFAULT_PROFILE = "local"


def get_runtime_profile_name(explicit_name=None):
    candidate = (explicit_name or os.getenv("APP_ENV") or DEFAULT_PROFILE).strip().lower()
    if candidate not in SUPPORTED_PROFILES:
        return DEFAULT_PROFILE
    return candidate


def load_runtime_profile(profile_name=None):
    resolved = get_runtime_profile_name(profile_name)
    root = Path(__file__).resolve().parent.parent
    profile_path = root / "config" / "profiles" / f"{resolved}.json"
    with profile_path.open("r", encoding="utf-8") as f:
        return json.load(f)
