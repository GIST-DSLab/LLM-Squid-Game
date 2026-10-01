"""Central prompt loading utility."""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_PROMPTS_DIR = Path(__file__).parent

_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=False,
    keep_trailing_newline=True,
)


#: Populated on the first render, not at import time. ``core.carrot``
#: lives under ``squid_game.core``, whose package ``__init__`` imports
#: the engine and therefore this module -- importing it up here would
#: close the cycle. Nothing can render before ``core`` is importable, so
#: the first call is a safe place to do it.
_carrot_globals_loaded = False


def _install_carrot_globals() -> None:
    """Expose the carrot vocabulary table to every template, once.

    Templates that state the accumulated thing (``1-game_intro.j2``,
    ``threat_type/_frame.j2``, ``5-forfeit_option.j2``,
    ``3-confidence_call.j2``) read one row of
    :data:`squid_game.core.carrot.CARROT_VOCABULARY`. Callers normally
    pass the row itself as ``carrot_vocab``; the global is the fallback
    for a render that passes only the name (``carrot=``) or only the
    deprecated boolean (``flagship_pull=``), which is what the type-D
    tests and a handful of dev scripts do.
    """
    global _carrot_globals_loaded
    if _carrot_globals_loaded:
        return
    from squid_game.core.carrot import CARROT_VOCABULARY

    _env.globals["CARROT_VOCABULARY"] = CARROT_VOCABULARY
    _carrot_globals_loaded = True


def render(template_path: str, **kwargs: object) -> str:
    """Render a prompt template relative to prompts/.

    Args:
        template_path: e.g. "legacy/forfeit_option.j2"
        **kwargs: Template variables.
    """
    _install_carrot_globals()
    template = _env.get_template(template_path)
    return template.render(**kwargs)
