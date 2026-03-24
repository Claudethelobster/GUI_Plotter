# ui/splash_screen.py
import sys
import time
import importlib
import random
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar, QApplication

EGG_FACTS = [
    "A standard chef's hat has 100 folds, representing 100 ways to cook an egg.",
    "The colour of an eggshell is determined purely by the breed of the hen.",
    "To tell if an egg is raw or hard-boiled, spin it. Raw eggs wobble, boiled ones spin cleanly.",
    "Eggs age more in one day at room temperature than in one week in the fridge.",
    "The stringy white bits keeping the yolk in the centre are called chalazae.",
    "As a hen ages, she lays larger eggs with much thinner shells.",
    "Kiwi birds lay the largest egg in relation to their body size of any bird.",
    "Ostrich eggs are the largest bird eggs, but the smallest in relation to the mother's size.",
    "Double-yolk eggs are typically laid by young hens whose reproductive systems haven't fully matured.",
    "The word 'yolk' derives from the Old English word 'geoloca', simply meaning 'yellow'.",
    "An average eggshell has up to 17,000 tiny microscopic pores over its surface.",
    "A hen turns her egg nearly 50 times a day to keep the yolk from sticking to the side.",
    "It takes a hen roughly 24 to 26 hours to produce a single egg.",
    "The UK consumes over 13 billion eggs every single year.",
    "Araucana hens are famous for laying natural pale blue or green eggs.",
    "Harriet, a hen from the UK, laid a record-breaking egg measuring 9.1 inches in diameter in 2010.",
    "Egg yolks are one of the few foods that naturally contain Vitamin D.",
    "If an egg sinks in a bowl of water, it is fresh. If it floats, it has gone bad.",
    "Blood spots in an egg do not mean it is fertilised; they are just a ruptured blood vessel.",
    "Cloudy egg whites are a sign that the egg is incredibly fresh.",
    "To peel a hard-boiled egg easily, plunge it into ice water immediately after cooking.",
    "The Guinness World Record for making an omelette is 427 in just 30 minutes.",
    "An eggshell is made almost entirely of calcium carbonate, the same material as chalk and limestone.",
    "The yolk and the white contain roughly the same amount of protein.",
    "Hens with white earlobes generally lay white eggs, whilst hens with red earlobes lay brown ones.",
    "A hen can lay unfertilised eggs without a cockerel being present.",
    "The thickest part of an eggshell is at the pointy end.",
    "Brown eggs are generally more expensive because the hens that lay them are larger and require more feed.",
    "A 'pullet' is a young hen under one year old, and their eggs are highly prized by pastry chefs.",
    "Eggs absorb odours easily because of their porous shells, which is why they are best kept in their cartons.",
    "The longest recorded flight of a tossed fresh egg without breaking is a staggering 98.51 metres.",
    "Quail eggs have a distinctly higher yolk-to-white ratio than chicken eggs, making them much richer in flavour.",
    "Fake eggs were once a serious counterfeit industry in the late 19th and early 20th centuries.",
    "The yolk colour is influenced entirely by a hen's diet; more marigold petals or maize means a deeper orange.",
    "To perfectly poach an egg, adding a splash of vinegar to the water helps coagulate the white faster.",
    "Hummingbird eggs can be as tiny as a baked bean.",
    "There is no nutritional difference whatsoever between brown and white eggs.",
    "A hen requires roughly 14 hours of daylight to trigger the egg-laying process.",
    "The phrase 'walking on eggshells' originated in the mid-19th century to describe acting with extreme caution.",
    "An egg will spin significantly faster if it is hard-boiled compared to a raw one because the liquid centre absorbs the momentum."
]

class SplashLoader(QWidget):
    def __init__(self):
        super().__init__()
        # Make it a frameless floating window that stays on top
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setFixedSize(450, 180) # Slightly wider and taller for the fact text
        self.setStyleSheet("background-color: #2b2b2b; color: white; border: 2px solid #555; border-radius: 8px;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        title = QLabel("EggPlot Data Plotter")
        title.setStyleSheet("font-size: 20px; font-weight: bold; border: none;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        self.status_label = QLabel("Initialising...")
        self.status_label.setStyleSheet("font-size: 12px; color: #aaa; border: none;")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        self.progress = QProgressBar()
        self.progress.setStyleSheet("""
            QProgressBar { border: 1px solid #555; border-radius: 4px; text-align: center; color: white; font-weight: bold; }
            QProgressBar::chunk { background-color: #0055ff; border-radius: 3px; }
        """)
        layout.addWidget(self.progress)
        
        # --- NEW: Random Egg Fact Label ---
        self.fact_label = QLabel(f"Did you know? {random.choice(EGG_FACTS)}")
        self.fact_label.setWordWrap(True)
        self.fact_label.setAlignment(Qt.AlignCenter)
        self.fact_label.setStyleSheet("font-size: 11px; font-style: italic; color: #888; border: none; padding-top: 10px;")
        layout.addWidget(self.fact_label)

    def load_heavy_modules(self):
        """ Sequentially imports heavy libraries and updates the UI. """
        
        # Add any modules here that cause startup lag
        modules_to_load = [
            ("numpy", "Loading numerical engine..."),
            ("scipy", "Loading scientific libraries..."),
            ("scipy.optimize", "Loading optimisation routines..."),
            ("scipy.signal", "Loading signal processing..."),
            ("pyqtgraph", "Loading graphics engine..."),
            ("matplotlib", "Loading colour maps..."),
            ("h5py", "Loading HDF5 support...")
        ]
        
        total = len(modules_to_load)
        
        for i, (mod_name, desc) in enumerate(modules_to_load):
            self.status_label.setText(desc)
            self.progress.setValue(int((i / total) * 100))
            
            # 1. Force the widget to physically redraw the text right now
            self.repaint() 
            # 2. Process any pending OS events
            QApplication.processEvents()
            # 3. Give the monitor 50 milliseconds to actually display the frame
            time.sleep(0.05) 
            
            try:
                importlib.import_module(mod_name)
            except ImportError:
                pass 
                
        # --- Change colour to green and text, but keep it full ---
        self.progress.setValue(100)
        self.status_label.setText("Building main window...")
        
        # Dynamically swap the chunk colour to green to indicate a successful load
        self.progress.setStyleSheet("""
            QProgressBar { border: 1px solid #555; border-radius: 4px; text-align: center; color: white; font-weight: bold; }
            QProgressBar::chunk { background-color: #28a745; border-radius: 3px; }
        """)
        self.progress.setFormat("Please wait...")
        
        # Force the OS to paint this final frame before the thread locks
        self.repaint()
        QApplication.processEvents()
        
        # A tiny sleep just to ensure the monitor physically draws the green bar
        time.sleep(0.1)
