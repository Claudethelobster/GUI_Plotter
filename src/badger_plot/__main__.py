# main.py
import sys
import os

# --- THE SPYDER CACHE ASSASSIN ---
# Spyder forcefully injects its own PyQt5 environment variables 
# into the external terminal. We must destroy them before PyQt6 loads.
os.environ.pop("QT_API", None)
os.environ.pop("QT_PLUGIN_PATH", None)
os.environ.pop("QT_QPA_PLATFORM_PLUGIN_PATH", None)
# ---------------------------------

# Now it is safe to import PyQt6
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

# --- Path Resolution ---
# Adds path of package to working directory. Both old and new dir will work.
# We do this at the top so all subsequent imports succeed.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the lightweight splash screen first
try:
    from badger_plot.ui.splash_screen import SplashLoader
except ModuleNotFoundError:
    from ui.splash_screen import SplashLoader

def main():
    # PyQt6 handles DPI scaling and OpenGL contexts natively under the hood!
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    # 1. Instantiate and reveal the Splash Screen immediately
    splash = SplashLoader()
    splash.show()
    
    splash.load_heavy_modules()
    
    # IMPORT HAPPENS HERE, NOWHERE ELSE!
    try: 
        from badger_plot.ui.main_window import BadgerLoopQtGraph
    except ModuleNotFoundError: 
        from ui.main_window import BadgerLoopQtGraph

    window = BadgerLoopQtGraph()
    splash.close()
    window.show()
    
    # PyQt6 uses .exec() instead of the legacy .exec_()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()