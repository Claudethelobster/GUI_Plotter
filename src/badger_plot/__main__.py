# main.py
import sys
import os
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

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
    # --- THE DEFINITIVE FIX FOR DEDICATED GPUs ---
    # Ensure OpenGL contexts share resources. Must be called before app creation.
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)

    # --- ENABLE 2D HARDWARE ACCELERATION ---
    # Optional: pushes all 2D panning, zooming, and drawing to the Graphics Card
    # import pyqtgraph as pg
    # pg.setConfigOptions(useOpenGL=True, antialias=True)

    # Safely get or create the QApplication instance
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
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
