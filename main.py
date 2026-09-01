"""Thin shim. The canonical entry point is ``uv run squid-game``.

Kept so ``python main.py --config ...`` keeps working for anyone with it in
muscle memory or in a script. It owns no argument parsing: everything,
including the ``.env`` load, lives in ``squid_game.runner.main``.
"""

from squid_game.runner import main

if __name__ == "__main__":
    main()
