class ThemeManager:
    def __init__(self):
        self.is_dark = False
        self.update(False)

    def update(self, is_dark):
        self.is_dark = is_dark
        if is_dark:
            # Dark Mode Palette
            self.bg = "#353535"
            self.fg = "#ffffff"
            self.panel_bg = "#222222"
            self.border = "#555555"
            
            self.primary_text = "#66a3ff"  # Brighter blue for dark backgrounds
            self.primary_bg = "#1a3355"
            self.primary_border = "#336699"
            
            self.danger_text = "#ff6666"   # Brighter red
            self.danger_bg = "#4d1a1a"
            self.danger_border = "#993333"
            
            self.success_text = "#50c878"  # Brighter green
            self.success_bg = "#1a4026"
            self.success_border = "#2d7344"
            
            self.warning_text = "#ffcc00"
            self.warning_bg = "#4d3d00"
            self.warning_border = "#997a00"
        else:
            # Light Mode Palette
            self.bg = "#f5f5f5"
            self.fg = "#000000"
            self.panel_bg = "#ffffff"
            self.border = "#8a8a8a"
            
            self.primary_text = "#0055ff"
            self.primary_bg = "#d0e8ff"
            self.primary_border = "#0055ff"
            
            self.danger_text = "#d90000"
            self.danger_bg = "#ffe6e6"
            self.danger_border = "#d90000"
            
            self.success_text = "#2ca02c"
            self.success_bg = "#e6f5e6"
            self.success_border = "#2ca02c"
            
            self.warning_text = "#ffaa00"
            self.warning_bg = "#fff0d0"
            self.warning_border = "#ffaa00"

# Global singleton so all dialogs can import and read the same colors
theme = ThemeManager()
