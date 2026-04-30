"""Central prompt loading utility."""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_PROMPTS_DIR = Path(__file__).parent

_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=False,
    keep_trailing_newline=True,
)


def render(template_path: str, **kwargs: object) -> str:
    """Render a prompt template relative to prompts/.

    Args:
        template_path: e.g. "forfeit/forfeit_option.j2"
        **kwargs: Template variables.
    """
    template = _env.get_template(template_path)
    return template.render(**kwargs)
