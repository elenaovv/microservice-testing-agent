from pathlib import Path
from string import Template

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def render_template(name: str, values: dict[str, object]) -> str:
    path = TEMPLATES_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    template = Template(path.read_text(encoding="utf-8"))
    normalized = {key: str(value) for key, value in values.items()}
    return template.safe_substitute(normalized).strip()
