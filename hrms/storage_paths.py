from pathlib import Path


def get_data_directory() -> Path:
    source_data = Path(__file__).resolve().parent.parent / "data"
    if (source_data / "hr_policies.json").is_file():
        return source_data
    return Path.cwd() / "data"
