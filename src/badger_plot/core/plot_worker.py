# core/plot_worker.py
import time
import traceback
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal # <-- Updated to PyQt6

class PlotWorkerThread(QThread):
    progress = pyqtSignal(int, str)
    finished_2d = pyqtSignal(list, bool) 
    finished_3d = pyqtSignal(list, tuple) 
    finished_heatmap = pyqtSignal(dict)   
    error = pyqtSignal(str)

    def __init__(self, dataset, params):
        super().__init__()
        self.dataset = dataset
        self.p = params

    def run(self):
        try:
            p = self.p
            mode = p["plot_mode"]
            sweeps = p["sweeps"]
            points = p["points"]
            xlog, ylog = p["xlog"], p["ylog"]
            zlog = p.get("zlog", False)
            xbase, ybase = p["xbase"], p["ybase"]
            zbase = p.get("zbase", 10.0)
            is_csv = (p["file_type"] == "CSV")
            
            active_series = p.get("active_series", [])
            if not active_series:
                raise ValueError("No data series selected to plot.")
                
            total_sweeps = len(sweeps)
            
            def get_fast_xyz(sw, pair):
                try:
                    if is_csv: arr = self.dataset.data
                    else: arr = self.dataset.sweeps[sw].data
                    
                    if points != -1: arr = arr[points]
                    
                    x_data = arr[:, pair['x']]
                    y_data = arr[:, pair['y']]
                    z_data = arr[:, pair['z']] if 'z' in pair and pair['z'] < arr.shape[1] else np.zeros_like(x_data)
                    
                    if mode == "2D": return x_data, y_data
                    else: return x_data, y_data, z_data
                except Exception:
                    empty = np.array([], dtype=np.float64)
                    if mode == "2D": return empty, empty
                    else: return empty, empty, empty

            # ============================================================
            # 2D MODE
            # ============================================================
            if mode == "2D":
                packages = []
                cmaps = ['Blues', 'Oranges', 'Greens', 'Reds', 'Purples', 'Greys']
                
                for pair_idx, pair in enumerate(active_series):
                    if not pair.get("visible", True):
                        continue
                    
                    cmap_name = cmaps[pair_idx % len(cmaps)]
                    
                    for i, sw in enumerate(sweeps):
                        prog = int(((pair_idx * total_sweeps + i) / (len(active_series) * total_sweeps)) * 100)
                        self.progress.emit(prog, f"Crunching Series {pair_idx+1}, Sweep {i+1}...")
                        
                        x, y = get_fast_xyz(sw, pair)
                        x, y = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
                        
                        x_name_out = pair.get("x_name", "X")
                        y_name_out = pair.get("y_name", "Y")

                        # =======================================================
                        # FFT MODE LOGIC - Done BEFORE Log Scaling!
                        # =======================================================
                        if p.get("fft_mode_active", False):
                            valid_fft = np.isfinite(x) & np.isfinite(y)
                            x_f, y_f = x[valid_fft], y[valid_fft]
                            if len(x_f) >= 2:
                                # Must sort data chronologically so time-delta (dt) is physically correct!
                                sort_idx = np.argsort(x_f)
                                x_f, y_f = x_f[sort_idx], y_f[sort_idx]
                                
                                dt = np.abs(x_f[-1] - x_f[0]) / max(1, len(x_f) - 1)
                                if dt > 0:
                                    window = np.hanning(len(y_f))
                                    y_wind = y_f * window
                                    
                                    yf = np.fft.rfft(y_wind)
                                    xf = np.fft.rfftfreq(len(y_wind), d=dt)
                                    
                                    mag = np.abs(yf) * 2.0 / len(y_wind)
                                    
                                    if len(xf) > 1:
                                        xf = xf[1:]
                                        mag = mag[1:]
                                        
                                    x, y = xf, mag
                                    
                            x_name_out = f"Frequency (Hz) [1/{pair.get('x_name', 'X')}]"
                            y_name_out = f"Magnitude [{pair.get('y_name', 'Y')}]"
                        # =======================================================

                        # Apply Log Scales AFTER FFT (or normally for Time Domain)
                        with np.errstate(divide='ignore', invalid='ignore'):
                            if xlog:
                                mask = x > 0
                                x, y = np.log(x[mask]) / np.log(xbase), y[mask]
                            if ylog:
                                mask = y > 0
                                x, y = x[mask], np.log(y[mask]) / np.log(ybase)
                                
                        valid = np.isfinite(x) & np.isfinite(y)
                        x, y = x[valid], y[valid]
                        
                        if len(x) == 0: continue
                        
                        pkg = {
                            "i": i, 
                            "sw": sw,
                            "pair_idx": pair_idx, 
                            "cmap_name": cmap_name, 
                            "y_name": y_name_out,
                            "x_name": x_name_out,
                            "axis": pair.get("axis", "L")
                        }
                        
                        if p.get("average_enabled", False):
                            x_std, y_std = np.std(x), np.std(y)
                            pkg.update({
                                "type": "average", 
                                "x_mean": np.mean(x), 
                                "y_mean": np.mean(y), 
                                "x_std": x_std, 
                                "y_std": y_std
                            })
                            if p.get("errorbars_enabled", False):
                                nsigma = p.get("nsigma", 1.0)
                                pkg["dx"], pkg["dy"] = nsigma * x_std, nsigma * y_std
                            packages.append(pkg)
                        else:
                            MAX_POINTS = 15000
                            if len(x) > MAX_POINTS:
                                stride = max(1, len(x) // MAX_POINTS)
                                x, y = x[::stride], y[::stride]
                                
                            pkg.update({
                                "type": "standard", 
                                "x": np.ascontiguousarray(x, dtype=np.float64), 
                                "y": np.ascontiguousarray(y, dtype=np.float64)
                            })
                            packages.append(pkg)
                            
                self.progress.emit(100, "Drawing Plot...")
                self.finished_2d.emit(packages, True)
                
            # ============================================================
            # HISTOGRAM MODE
            # ============================================================
            elif mode == "Histogram":
                packages = []
                cmaps = ['Blues', 'Oranges', 'Greens', 'Reds', 'Purples', 'Greys']
                
                # Fetch bins parameter (passed from the new UI box)
                bin_input = p.get("bins", "auto")
                try: bins = int(bin_input)
                except ValueError: bins = "auto"
                
                for pair_idx, pair in enumerate(active_series):
                    if not pair.get("visible", True): continue
                    cmap_name = cmaps[pair_idx % len(cmaps)]
                    
                    self.progress.emit(20, f"Aggregating data for {pair['y_name']}...")
                    
                    # Fetch all sweeps for this Y variable
                    agg_y = []
                    for sw in sweeps:
                        # Catch all returned variables in a tuple, then extract index 1 (the Y array)
                        res = get_fast_xyz(sw, pair)
                        y = res[1] 
                        agg_y.append(np.asarray(y, dtype=np.float64))
                        
                    if not agg_y: continue
                    y_all = np.concatenate(agg_y)
                    
                    # Apply log scaling if requested
                    if ylog:
                        mask = y_all > 0
                        y_all = np.log(y_all[mask]) / np.log(ybase)
                        
                    y_valid = y_all[np.isfinite(y_all)]
                    if len(y_valid) == 0: continue
                    
                    self.progress.emit(70, f"Calculating distribution for {pair.get('y_name', 'Y')}...")
                    
                    import scipy.stats as sp_stats
                    
                    stat_n = len(y_valid)
                    stat_mean = float(np.mean(y_valid))
                    stat_median = float(np.median(y_valid))
                    stat_std = float(np.std(y_valid))
                    stat_min = float(np.min(y_valid))
                    stat_max = float(np.max(y_valid))
                    
                    # Fallbacks in case the variance is strictly zero
                    try: stat_skew = float(sp_stats.skew(y_valid))
                    except: stat_skew = 0.0
                    try: stat_kurt = float(sp_stats.kurtosis(y_valid))
                    except: stat_kurt = 0.0

                    # --- NEW: Safe Binning Engine ---
                    if np.ptp(y_valid) == 0:
                        safe_bins = 10
                    else:
                        safe_bins = bins
                        
                    try:
                        counts, bin_edges = np.histogram(y_valid, bins=safe_bins)
                    except Exception:
                        counts, bin_edges = np.histogram(y_valid, bins=50)
                    # --------------------------------
                    
                    # Package it for the renderer
                    packages.append({
                        "type": "histogram",
                        "pair_idx": pair_idx,
                        "y_name": pair.get("y_name", "Y"),
                        "counts": counts.astype(np.float64), 
                        "bin_edges": bin_edges.astype(np.float64), 
                        "cmap_name": cmap_name,
                        "axis": pair.get("axis", "L"),
                        "stats": {
                            "n": stat_n, "mean": stat_mean, "median": stat_median, "std": stat_std,
                            "min": stat_min, "max": stat_max, "skew": stat_skew, "kurt": stat_kurt
                        }
                    })
                    
                self.progress.emit(100, "Drawing Histogram...")
                self.finished_2d.emit(packages, True) # We can reuse the 2D signal!

            # ============================================================
            # 3D MODE
            # ============================================================
            elif mode == "3D":
                pair = active_series[0] 
                all_pts_raw = []
                
                mins = np.array([np.inf, np.inf, np.inf])
                maxs = np.array([-np.inf, -np.inf, -np.inf])
                
                if p.get("graphtype") == "Surface":
                    self.progress.emit(20, "Extracting Surface Data streams...")
                    xs, ys, zs = [], [], []
                    
                    for sw in sweeps:
                        x, y, z = get_fast_xyz(sw, pair)
                        xs.append(x); ys.append(y); zs.append(z)
                        
                    x_arrs = np.concatenate(xs).astype(np.float64)
                    y_arrs = np.concatenate(ys).astype(np.float64)
                    z_arrs = np.concatenate(zs).astype(np.float64)
                    
                    with np.errstate(divide='ignore', invalid='ignore'):
                        if xlog: mask = x_arrs>0; x_arrs, y_arrs, z_arrs = np.log(x_arrs[mask])/np.log(xbase), y_arrs[mask], z_arrs[mask]
                        if ylog: mask = y_arrs>0; x_arrs, y_arrs, z_arrs = x_arrs[mask], np.log(y_arrs[mask])/np.log(ybase), z_arrs[mask]
                        if zlog: mask = z_arrs>0; x_arrs, y_arrs, z_arrs = x_arrs[mask], y_arrs[mask], np.log(z_arrs[mask])/np.log(zbase)
                        
                    valid = np.isfinite(x_arrs) & np.isfinite(y_arrs) & np.isfinite(z_arrs)
                    x_arrs, y_arrs, z_arrs = x_arrs[valid], y_arrs[valid], z_arrs[valid]
                    
                    if len(x_arrs) == 0: raise ValueError("No valid data points left!")

                    # ---> NEW: THE ANTI-HANG SHIELD FOR 3D SURFACES <---
                    MAX_SURFACE_POINTS = 50000
                    if len(x_arrs) > MAX_SURFACE_POINTS:
                        self.progress.emit(55, "Downsampling for fast meshing...")
                        stride = max(1, len(x_arrs) // MAX_SURFACE_POINTS)
                        x_arrs = x_arrs[::stride]
                        y_arrs = y_arrs[::stride]
                        z_arrs = z_arrs[::stride]
                    # ---------------------------------------------------
                    
                    mins = np.array([x_arrs.min(), y_arrs.min(), z_arrs.min()])
                    maxs = np.array([x_arrs.max(), y_arrs.max(), z_arrs.max()])
                    
                    self.progress.emit(60, "Meshing 3D Topographical Grid...")
                    import scipy.interpolate
                    
                    x_1d = np.linspace(mins[0], maxs[0], 100)
                    y_1d = np.linspace(mins[1], maxs[1], 100)
                    grid_x, grid_y = np.meshgrid(x_1d, y_1d, indexing='ij')
                    
                    try:
                        grid_z = scipy.interpolate.griddata((x_arrs, y_arrs), z_arrs, (grid_x, grid_y), method='linear')
                        if np.isnan(grid_z).any():
                            z_nearest = scipy.interpolate.griddata((x_arrs, y_arrs), z_arrs, (grid_x, grid_y), method='nearest')
                            grid_z[np.isnan(grid_z)] = z_nearest[np.isnan(grid_z)]
                    except Exception as e:
                        if "qhull" in str(e).lower() or "coplanar" in str(e).lower():
                            self.error.emit("Data is 1-Dimensional.\n\nSurface plots require a 2D area to stretch a surface over.")
                            return 
                        raise e
                        
                    # --- FIX: INCLUDE RAW POINTS FOR THE CROSSHAIR TO SNAP TO ---    
                    surface_dict = {
                        "x_1d": x_1d, "y_1d": y_1d, "z_2d": grid_z, 
                        "raw_pts": np.column_stack((x_arrs, y_arrs, z_arrs))
                    }
                    all_pts_raw.append(("SURFACE", 0, surface_dict))
                    
                else:
                    for i, sw in enumerate(sweeps):
                        self.progress.emit(int((i/total_sweeps)*90), f"Extracting 3D Data: Sweep {i}/{total_sweeps}...")
                        x, y, z = get_fast_xyz(sw, pair)
                        x, y, z = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64), np.asarray(z, dtype=np.float64)
                        
                        with np.errstate(divide='ignore', invalid='ignore'):
                            if xlog: mask = x>0; x, y, z = np.log(x[mask])/np.log(xbase), y[mask], z[mask]
                            if ylog: mask = y>0; x, y, z = x[mask], np.log(y[mask])/np.log(ybase), z[mask]
                            if zlog: mask = z>0; x, y, z = x[mask], y[mask], np.log(z[mask])/np.log(zbase)
                            
                        valid = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
                        x, y, z = x[valid], y[valid], z[valid]
                        
                        if len(x) > 0:
                            pts = np.column_stack((x, y, z))
                            mins = np.minimum(mins, pts.min(axis=0))
                            maxs = np.maximum(maxs, pts.max(axis=0))
                            
                            MAX_3D_POINTS = 50000
                            if len(pts) > MAX_3D_POINTS:
                                pts = pts[::len(pts)//MAX_3D_POINTS]
                                
                            all_pts_raw.append((i, sw, pts))
                            
                if np.any(np.isinf(mins)):
                    mins, maxs = np.zeros(3), np.ones(3)
                        
                self.progress.emit(100, "Rendering 3D OpenGL Scene...")
                self.finished_3d.emit(all_pts_raw, (mins, maxs))

            # ============================================================
            # HEATMAP MODE (Defaults to the first pair in the list)
            # ============================================================
            elif mode == "Heatmap":
                pair = active_series[0]
                self.progress.emit(10, "Fetching Heatmap Data Streams...")
                xs, ys, zs = [], [], []
                
                for i, sw in enumerate(sweeps):
                    self.progress.emit(10 + int((i/total_sweeps)*30), f"Extracting Heatmap Data: Sweep {i}/{total_sweeps}...")
                    x, y, z = get_fast_xyz(sw, pair)
                    xs.append(x); ys.append(y); zs.append(z)
                    
                x_arrs = np.concatenate(xs).astype(np.float64)
                y_arrs = np.concatenate(ys).astype(np.float64)
                z_arrs = np.concatenate(zs).astype(np.float64)
                
                with np.errstate(divide='ignore', invalid='ignore'):
                    if xlog:
                        mask = x_arrs > 0
                        x_arrs, y_arrs, z_arrs = np.log(x_arrs[mask]) / np.log(xbase), y_arrs[mask], z_arrs[mask]
                    if ylog:
                        mask = y_arrs > 0
                        x_arrs, y_arrs, z_arrs = x_arrs[mask], np.log(y_arrs[mask]) / np.log(ybase), z_arrs[mask]
                    if zlog:
                        self.progress.emit(45, "Applying Z-Log transformations...")
                        mask = z_arrs > 0
                        x_arrs, y_arrs, z_arrs = x_arrs[mask], y_arrs[mask], np.log(z_arrs[mask]) / np.log(zbase)
                
                valid = np.isfinite(x_arrs) & np.isfinite(y_arrs) & np.isfinite(z_arrs)
                x_arrs, y_arrs, z_arrs = x_arrs[valid], y_arrs[valid], z_arrs[valid]
                
                if len(x_arrs) == 0:
                    raise ValueError("No valid data points left after log scale filtering!")

                # ---> NEW: THE ANTI-HANG SHIELD <---
                MAX_HEATMAP_POINTS = 50000
                if len(x_arrs) > MAX_HEATMAP_POINTS:
                    self.progress.emit(55, "Downsampling for fast meshing...")
                    stride = max(1, len(x_arrs) // MAX_HEATMAP_POINTS)
                    x_arrs = x_arrs[::stride]
                    y_arrs = y_arrs[::stride]
                    z_arrs = z_arrs[::stride]
                # -----------------------------------
                    
                self.progress.emit(60, "Meshing Data Grid...")
                
                import scipy.interpolate
                grid_x, grid_y = np.mgrid[x_arrs.min():x_arrs.max():200j, y_arrs.min():y_arrs.max():200j]
                
                # --- CRITICAL FIX: GRACEFULLY INTERCEPT QHULL ERRORS ---
                try:
                    grid_z = scipy.interpolate.griddata((x_arrs, y_arrs), z_arrs, (grid_x, grid_y), method='linear')
                except Exception as e:
                    if "qhull" in str(e).lower() or "coplanar" in str(e).lower():
                        self.error.emit("Data is 1-Dimensional.\n\nHeatmaps require a 2D area to stretch a surface over.\nYour selected X and Y columns form a perfectly straight line, so no surface can be drawn.\n\nPlease select independent X and Y variables.")
                        return 
                    else:
                        raise e
                
                if np.isnan(grid_z).any():
                    self.progress.emit(80, "Filling boundary gaps...")
                    z_nearest = scipy.interpolate.griddata((x_arrs, y_arrs), z_arrs, (grid_x, grid_y), method='nearest')
                    grid_z[np.isnan(grid_z)] = z_nearest[np.isnan(grid_z)]
                    
                res_dict = {
                    "img_data": grid_z,
                    "x_min": x_arrs.min(), "x_max": x_arrs.max(),
                    "y_min": y_arrs.min(), "y_max": y_arrs.max(),
                    "z_min": grid_z.min(), "z_max": grid_z.max(),
                    "z_axis_name": pair.get("z_name", "Z")
                }
                
                self.progress.emit(100, "Rendering Heatmap Surface...")
                self.finished_heatmap.emit(res_dict)

        except Exception as e:
            traceback.print_exc()
            self.error.emit(str(e))
            
class BackgroundWorker(QThread):
    """Runs heavy maths and evaluations in the background to prevent GUI freezing."""
    finished = pyqtSignal(object) 
    error = pyqtSignal(str)

    def __init__(self, func, *args):
        super().__init__()
        self.func = func
        self.args = args

    def run(self):
        try:
            result = self.func(*self.args)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
