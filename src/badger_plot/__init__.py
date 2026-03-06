from badger_plot import core
from badger_plot import ui
from badger_plot import utils

try:
    from badger_plot import badger_loop_py3_3 # Ignore warning
except ImportError: # Error handled in core.dataloader
    pass

from badger_plot.__main__ import main

# Give main import alias
run = main
badger_plot = main


__all__ = [
    "main",
    "run",
    "badger_plot",
    "core", 
    "ui", 
    "utils",
    ]

