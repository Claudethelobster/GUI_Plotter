from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QPushButton, QTabWidget, QWidget

from core.theme import theme

class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EggPlot - Help & Instructions")
        self.resize(950, 750)
        
        # Apply the base dialog theme
        self.setStyleSheet(f"background-color: {theme.bg}; color: {theme.fg};")

        layout = QVBoxLayout(self)
        
        # Shared CSS string to inject dynamic theme colours into all tabs
        self.css = f"""
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; font-size: 14px; color: {theme.fg}; line-height: 1.5; }}
            h2 {{ color: {theme.danger_text}; border-bottom: 2px solid {theme.border}; padding-bottom: 4px; margin-top: 15px; font-size: 20px; }}
            h3 {{ color: {theme.primary_text}; margin-top: 15px; margin-bottom: 4px; font-size: 16px; }}
            ul {{ margin-top: 5px; }}
            li {{ margin-bottom: 8px; }}
            code {{ background-color: {theme.bg}; padding: 2px 5px; border-radius: 4px; font-family: Consolas, monospace; color: {theme.primary_text}; font-weight: bold; border: 1px solid {theme.border}; }}
            .about {{ background-color: {theme.warning_bg}; border-left: 4px solid {theme.warning_border}; padding: 12px; margin-bottom: 20px; font-style: italic; color: {theme.fg}; }}
            .safety {{ background-color: {theme.primary_bg}; border-left: 4px solid {theme.primary_border}; padding: 12px; margin-top: 15px; margin-bottom: 15px; color: {theme.fg}; }}
        </style>
        """

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Build the tabs
        self._build_welcome_tab()
        self._build_2d_tab()
        self._build_3d_tab()
        self._build_heatmap_tab()
        self._build_histogram_tab()

        close_btn = QPushButton("Close Guide")
        close_btn.setFixedWidth(120)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {theme.panel_bg}; border: 1px solid {theme.border}; border-radius: 4px; padding: 8px; color: {theme.fg}; font-weight: bold; }}
            QPushButton:hover {{ background-color: {theme.bg}; }}
        """)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def _create_browser(self, html_body):
        """Helper function to generate a styled QTextBrowser for each tab."""
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setStyleSheet(f"background-color: {theme.panel_bg}; border: 1px solid {theme.border}; padding: 10px;")
        browser.setHtml(self.css + html_body)
        return browser

    def _build_welcome_tab(self):
        html = """
        <h2>Welcome to EggPlot</h2>
        
        <div class="about">
            <b>About EggPlot:</b> EggPlot earned its namesake during development when the validation engine accidentally loaded a grocery list containing "Eggs" instead of actual experimental data, attempting to plot the eggs against a time axis. Today, it stands as a multi-format analysis tool for physicists.
        </div>

        <div class="safety">
            <b>Data Protection (MIRROR Files)</b><br>
            To prevent accidental data loss, this software uses a strict <b>Mirror File System</b>. When modifying a file (e.g., renaming columns, generating custom math), the programme creates a safe copy prefixed with <code>MIRROR_</code> and applies the changes there. Your original raw data is never altered.<br><br>
            <i>Note: If you are working on a Concatenated CSV, the software assumes it is already a derived working file, so it applies changes directly.</i>
        </div>

        <h3>Global Preferences & Settings</h3>
        <ul>
            <li><b>Preferences Menu:</b> Access this via the main toolbar to configure the programme's core behaviour. Here you can set the global UI theme (Light/Dark/System), adjust the hardware polling rate for crosshairs (useful for optimising performance on older machines), and configure default startup directories and cache limits.</li>
        </ul>

        <h3>Opening & Inspecting Data</h3>
        <ul>
            <li><b>Open File:</b> Loads standard CSVs, HDF5 binaries (<code>.h5</code>), or native BadgerLoop (<code>.blp</code>) files.</li>
            <li><b>Open Folder (Batch CSVs):</b> Loads a directory of CSV files as "Sweeps" of the same experiment.</li>
            <li><b>Concatenate Folder:</b> Stitches a folder of CSVs into a single <code>ConcatenatedCSV</code> file, injecting inline metadata so sweep boundaries are remembered.</li>
            <li><b>Metadata & Sweep Table:</b> Click <i>Show Metadata</i> to view file details. Use <i>Inspect &rarr; Sweep table</i> to view raw numerical data.</li>
            <li><b>Custom Columns:</b> Navigate to <i>Inspect &rarr; Create custom column</i> to mathematically derive new data using standard NumPy equations.</li>
        </ul>

        <h3>Saving & Exporting</h3>
        <ul>
            <li><b>Save Plot:</b> Exports the current visualisation as a PNG, JPG, or scalable SVG file.</li>
            <li><b>Export Plotted Data:</b> Exports the specific arrays currently visible on the plot. You can overwrite an existing CSV or append the plotted data as new columns.</li>
        </ul>
        """
        self.tabs.addTab(self._create_browser(html), "Data & Basics")

    def _build_2d_tab(self):
        html = """
        <h2>2D Plotting Mode</h2>
        <p>The standard mode for analysing X-Y datasets. Overlays all active series in the list using standard Lines or Scatters.</p>
        
        <h3>Trace & Layout Customisation</h3>
        <ul>
            <li><b>Adding Data:</b> Select X and Y columns and click <b>Add Pair</b>. Click the L/R button on a trace to assign it to the Left or Right Y-Axis.</li>
            <li><b>Per-Trace Customisation:</b> Click the ⚙️ icon to set line style, thickness, colour, and scatter symbols for specific traces.</li>
            <li><b>Layout Manager (Ctrl+L):</b> A comprehensive control panel for the visual aesthetics of your plot. You can slice data streams (e.g., <code>0:10</code>), toggle grid line visibility and opacity, switch background/foreground colours, change axis line thickness, and dynamically tweak <b>Legend Cosmetics</b> (opacity, column count, and positioning) which update live as you drag the sliders.</li>
            <li><b>Font Controls:</b> The layout menu also allows you to globally adjust font families and sizes for titles, axis labels, and tick marks.</li>
        </ul>

        <h3>Interaction & Analysis</h3>
        <ul>
            <li><b>Crosshairs & Selection:</b> Toggle crosshairs (Ctrl+H) or use Box/Lasso selection. Highlighting points spawns a statistics box and acts as a <b>Math Mask</b> for downstream tools.</li>
            <li><b>Area Calculators:</b> Calculate Area Under Curve (definite integrals) or Enclosed Loop Area (e.g., Hysteresis) using the Shoelace formula.</li>
            <li><b>Signal Processing & Fourier:</b> Apply smoothing, moving averages, derivatives, STFT Spectrograms, or use the iFFT Surgeon to cut out noise frequencies.</li>
        </ul>

        <h3>2D Curve Fitting</h3>
        <ul>
            <li><b>Standard & Custom Functions:</b> Access the <b>Fitting</b> menu to apply Polynomial, Gaussian, Exponential, Lorentzian, or Logarithmic fits, or define your own mathematical function.</li>
            <li><b>Targeted Swarm Search:</b> If the local optimiser gets stuck, EggPlot will suggest running a global differential evolution swarm to hunt down the best starting parameters.</li>
            <li><b>Export Fit to Column:</b> Instantly turns your mathematical fit into hard data by generating an X-array spanning your data's bounds and evaluating the Y-values into new columns.</li>
        </ul>
        """
        self.tabs.addTab(self._create_browser(html), "2D Plot")

    def _build_3d_tab(self):
        html = """
        <h2>3D Plotting Mode</h2>
        <p>Visualise spatial or multi-variable datasets. <b>Requires X, Y, and Z columns to be assigned.</b> Displays the currently highlighted series.</p>
        
        <h3>3D Visualisation Options</h3>
        <ul>
            <li><b>3D Scatter:</b> Renders individual data points in 3D space. Useful for point clouds or disjointed spatial data.</li>
            <li><b>3D Line:</b> Connects your X, Y, Z coordinates sequentially. Ideal for tracking trajectories or orbits over time.</li>
            <li><b>Surface Mesh:</b> Renders a colour-mapped topological 3D surface. The engine interpolates your discrete data points into a solid, interactive terrain.</li>
        </ul>

        <h3>Controls & Interaction</h3>
        <ul>
            <li><b>Camera Navigation:</b> Click and drag to rotate the 3D grid. Right-click and drag to zoom. Middle-click and drag to pan the camera center.</li>
            <li><b>Scaling:</b> Use the layout settings to adjust the aspect ratio of the X, Y, and Z bounding boxes to prevent flattened or stretched axes.</li>
            <li><b>3D Crosshair:</b> An interactive 3D reticle that snaps to your data points in three-dimensional space, providing exact X, Y, and Z coordinate readouts on the topology.</li>
        </ul>

        <h3>3D Surface Fitting</h3>
        <ul>
            <li><b>Applying a Fit:</b> Navigate to the Fitting menu while in 3D mode to map a mathematical surface (e.g., 2D Gaussian, Polynomial plane) directly onto your spatial data.</li>
            <li><b>Visualising the Fit:</b> Renders the fitted equation as a semi-transparent surface overlaying your raw 3D scatter or line data.</li>
        </ul>
        """
        self.tabs.addTab(self._create_browser(html), "3D Plot")

    def _build_heatmap_tab(self):
        html = """
        <h2>Heat Map Mode</h2>
        <p>A flat, 2D representation of 3D data. <b>Requires X, Y, and Z columns.</b></p>
        
        <h3>Features</h3>
        <ul>
            <li><b>Colour Mapping:</b> Generates a 2D grid where the X and Y axes represent coordinates, and the colour intensity of each pixel represents the Z value.</li>
            <li><b>Data Interpolation:</b> EggPlot automatically bins and interpolates scattered X, Y, Z data into a uniform grid required for heat map rendering.</li>
            <li><b>Colour Scales:</b> You can adjust the colour gradient map in the layout settings to better highlight specific thresholds or intensity peaks.</li>
        </ul>
        """
        self.tabs.addTab(self._create_browser(html), "Heat Map")

    def _build_histogram_tab(self):
        html = """
        <h2>Histogram Mode</h2>
        <p>Analyse the statistical distribution of a single variable. <b>Requires only a Y column to be assigned.</b></p>
        
        <h3>Features & Statistical Tools</h3>
        <ul>
            <li><b>Smart Binning Optimiser:</b> Automatically calculates the mathematically ideal number of bins for your specific dataset using established statistical rules, ensuring your distribution is never artificially over- or under-represented.</li>
            <li><b>Manual Bin Control:</b> Use the slider or input box on the left panel to manually override the optimiser and adjust the resolution of the distribution.</li>
            <li><b>Probability Density Function (PDF):</b> Overlays a smooth, continuous Gaussian KDE (Kernel Density Estimate) or fitted PDF curve directly on top of your discrete bins to better visualise the underlying continuous probability distribution.</li>
            <li><b>Sigma Clipper:</b> A powerful outlier rejection tool. Set a standard deviation threshold (e.g., 3-sigma), and the clipper will instantly filter out extreme anomalous values, recalculating the histogram and statistics without the noise.</li>
            <li><b>Statistics HUD:</b> Click <b>Toggle Histogram Stats</b> to view an on-screen overlay containing the dataset's Count, Mean, Median, Mode, Standard Deviation, Skewness, and Kurtosis.</li>
        </ul>
        """
        self.tabs.addTab(self._create_browser(html), "Histogram")
