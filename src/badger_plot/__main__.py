# main.py
import sys
import os
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

# Enable OpenGL hardware acceleration features in pyqtgraph
# import pyqtgraph as pg

# Import your newly modularized main window
try: # try the polite way
    from badger_plot.ui.main_window import BadgerLoopQtGraph
    
except ModuleNotFoundError: # bully it into submission
    # Adds path of package to working directory. Both old and new dir will work
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from badger_plot.ui.main_window import BadgerLoopQtGraph


def main():
    # --- THE DEFINITIVE FIX FOR DEDICATED GPUs ---
    # Ensure OpenGL contexts share resources. Must be called before app creation.
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)

    # --- ENABLE 2D HARDWARE ACCELERATION ---
    # Optional: pushes all 2D panning, zooming, and drawing to the Graphics Card
    # pg.setConfigOptions(useOpenGL=True, antialias=True)

    # Safely get or create the QApplication instance
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    window = BadgerLoopQtGraph()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":

    main()