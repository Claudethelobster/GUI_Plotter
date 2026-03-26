import os
import json
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, 
    QFormLayout, QCheckBox, QLineEdit, QPushButton, QLabel, 
    QSlider, QFileDialog, QMessageBox, QComboBox, QApplication
)
from core.theme import theme

class PreferencesDialog(QDialog):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.setWindowTitle("EggPlot Preferences")
        self.setMinimumWidth(450)
        self.main_window = main_window
        self.settings = main_window.settings
        
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        self._build_general_tab()
        self._build_ui_tab()
        self._build_advanced_tab()
        
        btn_box = QHBoxLayout()
        ok_btn = QPushButton("Save & Apply")
        ok_btn.setStyleSheet(f"font-weight: bold; color: {theme.primary_text}; padding: 6px;")
        cancel_btn = QPushButton("Cancel")
        
        ok_btn.clicked.connect(self._on_save_clicked)
        cancel_btn.clicked.connect(self.reject)
        
        btn_box.addStretch()
        btn_box.addWidget(cancel_btn)
        btn_box.addWidget(ok_btn)
        layout.addLayout(btn_box)
        
        self.load_current_settings()

    def _build_general_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        
        # Mirror File Settings
        self.mirror_subfolder = QCheckBox("Save Mirrors in /EggPlot_Output/ subfolder")
        form.addRow("File Management:", self.mirror_subfolder)
        
        form.addRow(QLabel("<hr>"))
        
        # Profile Management
        profile_lay = QHBoxLayout()
        btn_export = QPushButton("Export Profile")
        btn_import = QPushButton("Import Profile")
        btn_export.clicked.connect(self.export_profile)
        btn_import.clicked.connect(self.import_profile)
        profile_lay.addWidget(btn_export)
        profile_lay.addWidget(btn_import)
        form.addRow("Settings Profile:", profile_lay)
        
        self.portable_mode = QCheckBox("Portable Mode (Save settings to local .ini file)")
        self.portable_mode.setToolTip("Keeps settings in the app folder instead of the Windows Registry.")
        form.addRow("", self.portable_mode)
        
        form.addRow(QLabel("<hr>"))
        
        # Nuclear Option
        btn_reset = QPushButton("Reset to Factory Defaults")
        btn_reset.setStyleSheet(f"color: {theme.danger_text}; font-weight: bold;")
        btn_reset.clicked.connect(self.factory_reset)
        form.addRow("Memory Wipe:", btn_reset)
        
        self.tabs.addTab(tab, "General & Data")
        
    def _on_save_clicked(self):
        current_dyn = self.dynamic_res_cb.isChecked()
        current_mon = self.monitor_combo.currentData()
        current_res = self.resolution_combo.currentData()
        
        # 1. If we are in Fixed Mode AND the target monitor changed
        if not current_dyn and str(current_mon) != str(self.initial_monitor):
            ans = QMessageBox.question(
                self, "Restart Required", 
                "Changing the target monitor in Fixed Mode requires the programme to restart to apply the correct Windows scaling.\n\nWould you like to save and restart now?", 
                QMessageBox.Yes | QMessageBox.No
            )
            
            if ans == QMessageBox.Yes:
                self.requires_restart = True
                self.accept()
            else:
                # Revert UI back to original and abort the save
                self.dynamic_res_cb.setChecked(self.initial_dynamic)
                
                idx_mon = self.monitor_combo.findData(self.initial_monitor)
                if idx_mon >= 0: self.monitor_combo.setCurrentIndex(idx_mon)
                    
                idx_res = self.resolution_combo.findData(self.initial_resolution)
                if idx_res >= 0: self.resolution_combo.setCurrentIndex(idx_res)
                    
                return 
                
        # 2. If they just toggled dynamic mode, or changed resolution on the same monitor
        elif current_dyn != self.initial_dynamic or str(current_res) != str(self.initial_resolution):
            self.requires_restart = False
            self.accept()
            
        # 3. No display changes were made
        else:
            self.requires_restart = False
            self.accept()
            
    def _toggle_res_ui(self):
        """ Greys out the display/resolution selectors if Dynamic Mode is active. """
        is_dynamic = self.dynamic_res_cb.isChecked()
        self.monitor_combo.setEnabled(not is_dynamic)
        self.resolution_combo.setEnabled(not is_dynamic)

    def _build_ui_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        
        self.dark_mode = QCheckBox("Enable Dark Mode Theme (Requires Restart)")
        form.addRow("Application Theme:", self.dark_mode)
        
        form.addRow(QLabel("<hr>"))
        
        # --- NEW: WINDOW TARGETING & RESOLUTION ---
        self.dynamic_res_cb = QCheckBox("Enable dynamic resolution & free dragging")
        self.dynamic_res_cb.stateChanged.connect(self._toggle_res_ui)
        form.addRow("Window Mode:", self.dynamic_res_cb)
        
        self.monitor_combo = QComboBox()
        self.screens = QApplication.screens()
        
        for i, screen in enumerate(self.screens):
            # E.g., "Display 1 (1920x1080)"
            geom = screen.geometry()
            self.monitor_combo.addItem(f"Display {i + 1} ({geom.width()}x{geom.height()})", userData=i)
            
        self.resolution_combo = QComboBox()
        self.monitor_combo.currentIndexChanged.connect(self._update_resolutions)
        
        form.addRow("Target Monitor:", self.monitor_combo)
        form.addRow("Window Resolution:", self.resolution_combo)
        
        form.addRow(QLabel("<hr>"))
        # ------------------------------------------

        btn_restore_warnings = QPushButton("Restore all 'Are you sure?' warnings")
        btn_restore_warnings.clicked.connect(self.restore_warnings)
        form.addRow("Safety Nets:", btn_restore_warnings)
        
        self.tabs.addTab(tab, "UI & Experience")

    def _update_resolutions(self, index):
        """ Dynamically updates available resolutions based on the selected monitor's physical pixels. """
        self.resolution_combo.blockSignals(True) # Prevent recursive firing
        self.resolution_combo.clear()
        
        if index < 0 or index >= len(self.screens): 
            self.resolution_combo.blockSignals(False)
            return
            
        target_screen = self.screens[index]
        avail_geom = target_screen.availableGeometry() 
        scale_factor = target_screen.devicePixelRatio()
        
        # Calculate true physical workspace
        phys_w = int(avail_geom.width() * scale_factor)
        phys_h = int(avail_geom.height() * scale_factor)
        
        max_str = f"Maximise to Screen ({phys_w}x{phys_h})"
        self.resolution_combo.addItem(f"{max_str} (Recommended)", userData="MAX")
        
        standard_res = [
            (3840, 2160), (3440, 1440), (2560, 1600), (2560, 1440), 
            (2560, 1080), (1920, 1200), (1920, 1080), (1680, 1050), 
            (1600, 900),  (1440, 900),  (1366, 768),  (1280, 1024), 
            (1280, 800),  (1280, 720),  (1024, 768),  (800, 600)
        ]
        
        for w, h in standard_res:
            if w <= phys_w and h <= phys_h:
                self.resolution_combo.addItem(f"{w} x {h}", userData=f"{w}x{h}")
                
        saved_res = self.settings.value("target_resolution", "MAX")
        idx = self.resolution_combo.findData(saved_res)
        
        if idx >= 0:
            self.resolution_combo.setCurrentIndex(idx)
        else:
            # FALLBACK: If the old resolution doesn't fit the new monitor, revert to Maximise
            self.resolution_combo.setCurrentIndex(0)
            
        self.resolution_combo.blockSignals(False)

    def _build_advanced_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        
        self.disable_opengl = QCheckBox("Disable Hardware Acceleration (OpenGL)")
        self.disable_opengl.setToolTip("Check this if 3D plots are crashing your graphics driver.")
        form.addRow("Graphics:", self.disable_opengl)
        
        # Polling Rate Slider
        poll_lay = QHBoxLayout()
        self.poll_slider = QSlider(Qt.Horizontal)
        self.poll_slider.setRange(10, 120)
        self.poll_slider.setTickPosition(QSlider.TicksBelow)
        self.poll_slider.setTickInterval(10)
        
        self.poll_lbl = QLabel("60 Hz")
        self.poll_lbl.setFixedWidth(45)
        
        self.poll_slider.valueChanged.connect(lambda v: self.poll_lbl.setText(f"{v} Hz"))
        
        poll_lay.addWidget(self.poll_slider)
        poll_lay.addWidget(self.poll_lbl)
        form.addRow("Crosshair Polling Rate:", poll_lay)
        
        self.tabs.addTab(tab, "Advanced / Performance")

    def load_current_settings(self):
        self.mirror_subfolder.setChecked(self.settings.value("mirror_subfolder", False, bool))
        self.portable_mode.setChecked(self.settings.value("portable_mode", False, bool))
        self.dark_mode.setChecked(self.settings.value("dark_mode", False, bool))
        self.disable_opengl.setChecked(self.settings.value("disable_opengl", False, bool))
        
        poll_rate = int(self.settings.value("crosshair_poll_rate", 60))
        self.poll_slider.setValue(poll_rate)
        
        # --- Load Window Targeting & Store Initial States ---
        try:
            self.initial_monitor = int(self.settings.value("target_monitor", 0))
        except (ValueError, TypeError):
            self.initial_monitor = 0
            
        if self.initial_monitor < self.monitor_combo.count():
            self.monitor_combo.setCurrentIndex(self.initial_monitor)
        else:
            self.monitor_combo.setCurrentIndex(0)
            self.initial_monitor = 0
            
        self._update_resolutions(self.monitor_combo.currentIndex())
        
        self.initial_resolution = self.settings.value("target_resolution", "MAX")
        idx = self.resolution_combo.findData(self.initial_resolution)
        if idx >= 0:
            self.resolution_combo.setCurrentIndex(idx)
        else:
            self.initial_resolution = "MAX"
            
        # --- NEW: Load dynamic state and apply greying out ---
        self.initial_dynamic = self.settings.value("dynamic_resolution", False, bool)
        self.dynamic_res_cb.setChecked(self.initial_dynamic)
        self._toggle_res_ui()
        # -----------------------------------------------------
            
        self.requires_restart = False
        # ----------------------------------------------------

    def restore_warnings(self):
        self.settings.setValue("suppress_rename_warning", False)
        QMessageBox.information(self, "Restored", "All confirmation dialogs have been restored.")

    def factory_reset(self):
        ans = QMessageBox.warning(
            self, "Factory Reset", 
            "Are you sure you want to completely wipe all EggPlot settings, custom equations, and formatting defaults?\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        if ans == QMessageBox.Yes:
            self.settings.clear()
            QMessageBox.information(self, "Reset Complete", "Settings wiped. Please restart EggPlot.")
            self.accept()

    def export_profile(self):
        fname, _ = QFileDialog.getSaveFileName(self, "Export Profile", "EggPlot_Profile.json", "JSON Files (*.json)")
        if not fname: return
        
        # Dump all QSettings to a dictionary
        data = {key: self.settings.value(key) for key in self.settings.allKeys()}
        try:
            with open(fname, 'w') as f:
                json.dump(data, f, indent=4)
            QMessageBox.information(self, "Success", "Profile exported successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export profile:\n{e}")

    def import_profile(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Import Profile", "", "JSON Files (*.json)")
        if not fname: return
        
        try:
            with open(fname, 'r') as f:
                data = json.load(f)
            for key, val in data.items():
                self.settings.setValue(key, val)
            self.load_current_settings()
            QMessageBox.information(self, "Success", "Profile imported! Some changes may require a restart.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to import profile:\n{e}")

    def get_results(self):
        return {
            "mirror_subfolder": self.mirror_subfolder.isChecked(),
            "portable_mode": self.portable_mode.isChecked(),
            "dark_mode": self.dark_mode.isChecked(),
            "disable_opengl": self.disable_opengl.isChecked(),
            "crosshair_poll_rate": self.poll_slider.value(),
            "target_monitor": self.monitor_combo.currentData(),
            "target_resolution": self.resolution_combo.currentData(),
            "dynamic_resolution": self.dynamic_res_cb.isChecked() # <--- ADD THIS
        }
