# core/data_loader.py
import os
import csv
import time
import builtins
import traceback
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal # <-- Updated to PyQt6
import h5py

# --- SAFE IMPORT FOR NATIVE BADGERLOOP FILES ---
try:
    from badger_plot.badger_loop_py3_3 import Dataset
    BADGERLOOP_AVAILABLE = True
except ImportError:
    BADGERLOOP_AVAILABLE = False
    # Create a dummy class so the script doesn't throw NameErrors before catching it
    class Dataset: pass 



class TrackedFile:
    """A proxy wrapper that spies on file reading to calculate ETA and percentages."""
    def __init__(self, file_obj, file_size, callback, text_prefix="Loading"):
        self.file_obj = file_obj
        self.file_size = file_size
        self.callback = callback
        self.text_prefix = text_prefix
        self.bytes_read = 0
        self.start_time = time.time()
        self.last_update = 0

    def _update_progress(self, advance_bytes=0):
        self.bytes_read += advance_bytes
        now = time.time()
        # Update the UI a maximum of 15 times a second to prevent lag
        if now - self.last_update > 0.06 or self.bytes_read >= self.file_size:
            self.last_update = now
            percent = min(100, int((self.bytes_read / max(1, self.file_size)) * 100))
            elapsed = now - self.start_time
            rate = self.bytes_read / elapsed if elapsed > 0 else 0
            time_left = (self.file_size - self.bytes_read) / rate if rate > 0 else 0
            
            mins, secs = divmod(int(time_left), 60)
            time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
            
            self.callback(percent, f"{self.text_prefix}: {percent}% (Est. {time_str} left)")

    def read(self, size=-1):
        if size < 0:
            chunks = []
            chunk_size = 1024 * 1024  # 1 MB chunks
            while True:
                chunk = self.file_obj.read(chunk_size)
                if not chunk: break
                chunks.append(chunk)
                b_len = len(chunk.encode('utf-8')) if isinstance(chunk, str) else len(chunk)
                self._update_progress(b_len)
                
            return "".join(chunks) if chunks and isinstance(chunks[0], str) else b"".join(chunks) if chunks else ("" if isinstance(self.file_obj.read(0), str) else b"")
        else:
            data = self.file_obj.read(size)
            b_len = len(data.encode('utf-8')) if isinstance(data, str) else len(data)
            self._update_progress(b_len)
            return data

    def readline(self, *args):
        data = self.file_obj.readline(*args)
        b_len = len(data.encode('utf-8')) if isinstance(data, str) else len(data)
        self._update_progress(b_len)
        return data

    def readlines(self, hint=-1):
        lines = self.file_obj.readlines(hint)
        for line in lines:
            b_len = len(line.encode('utf-8')) if isinstance(line, str) else len(line)
            self._update_progress(b_len)
        return lines

    def __iter__(self): return self

    def __next__(self):
        try:
            line = next(self.file_obj)
        except StopIteration:
            raise StopIteration
        b_len = len(line.encode('utf-8')) if isinstance(line, str) else len(line)
        self._update_progress(b_len)
        return line
        
    def __getattr__(self, attr): return getattr(self.file_obj, attr)
    def __enter__(self): return self
    def __exit__(self, *args): self.file_obj.close()


class CSVSweep:
    """ A simple data container to mimic the BadgerLoop sweep structure for CSVs. """
    def __init__(self, data_array, name=""):
        self.data = data_array
        self.num_points = data_array.shape[0] if data_array.size else 0
        self.name = name

class MultiCSVDataset:
    """ Loads a validated list of CSV files into a single multi-sweep object. """
    def __init__(self, folder_path, file_list, delimiter=",", has_header=True):
        self.filename = folder_path  # The folder acts as the 'file' for saving mirrors
        self.file_list = file_list
        self.column_names = {}
        self.sweeps = []
        self.num_sweeps = 0
        self.num_points = 0
        self.num_inputs = 0
        self.num_outputs = 0
        self.notes = f"# Loaded from folder: {os.path.basename(folder_path)}\n"
        self._load_all(delimiter, has_header)

    def _load_all(self, delimiter, has_header):
        if delimiter == "auto": delimiter = ","

        for i, filepath in enumerate(self.file_list):
            with open(filepath, 'r', encoding='utf-8-sig', errors='ignore') as f:
                lines = f.readlines()
            
            headers_found = False
            sweep_data = []
            
            for line in lines:
                clean_line = line.strip()
                if not clean_line or clean_line.startswith("#"): continue
                
                if has_header and not headers_found:
                    if i == 0: # Only map columns from the first file
                        row = next(csv.reader([clean_line], delimiter=delimiter))
                        for col_idx, col_name in enumerate(row):
                            self.column_names[col_idx] = col_name.strip()
                        self.num_inputs = len(self.column_names)
                    headers_found = True
                    continue
                    
                row = next(csv.reader([clean_line], delimiter=delimiter))
                num_row = []
                for val in row:
                    try: num_row.append(float(val))
                    except ValueError: num_row.append(np.nan)
                sweep_data.append(num_row)
                
            arr = np.array(sweep_data, dtype=np.float64)
            self.sweeps.append(CSVSweep(arr, name=os.path.basename(filepath)))
            self.num_points += arr.shape[0]
            
        self.num_sweeps = len(self.sweeps)
        if self.num_sweeps > 0:
            self.data = np.vstack([s.data for s in self.sweeps]) # Flat fallback for legacy operations
        else:
            self.data = np.array([])


class CSVDataset:
    """ Loads a standard CSV, but now natively detects '# --- Sweep' concatenation markers! """
    def __init__(self, filename, delimiter=",", has_header=True):
        self.filename = filename
        self.column_names = {}
        self.data = None
        self.sweeps = []
        self.num_sweeps = 0
        self.num_points = 0
        self.num_inputs = 0
        self.num_outputs = 0
        self.notes = ""
        self._load_data(delimiter, has_header)

    def _load_data(self, delimiter, has_header):
        if delimiter == "auto": delimiter = ","
        
        with open(self.filename, 'r', encoding='utf-8-sig', errors='ignore') as f:
            lines = f.readlines()
            
        headers = []
        notes_lines = []
        current_sweep_data = []
        sweep_blocks = []
        
        self.is_concatenated = False

        for line in lines:
            clean_line = line.strip()
            if not clean_line: continue
            
            if clean_line.startswith("#"):
                # --- NEW FLAG DETECTION ---
                if "Format: ConcatenatedCSV" in clean_line:
                    self.is_concatenated = True
                # --------------------------

                if "--- Sweep" in clean_line:
                    if current_sweep_data:
                        sweep_blocks.append(current_sweep_data)
                        current_sweep_data = []
                notes_lines.append(clean_line) # Keep all comments in notes
                continue
                
            if has_header and not headers:
                row = next(csv.reader([clean_line], delimiter=delimiter))
                headers = [h.strip() for h in row]
                continue
                
            row = next(csv.reader([clean_line], delimiter=delimiter))
            num_row = []
            for val in row:
                try: num_row.append(float(val))
                except ValueError: num_row.append(np.nan)
            current_sweep_data.append(num_row)
            
        if current_sweep_data:
            sweep_blocks.append(current_sweep_data)
            
        self.notes = "\n".join(notes_lines)
        
        if not headers and sweep_blocks and sweep_blocks[0]:
            headers = [f"Column {i}" for i in range(len(sweep_blocks[0][0]))]
            
        for i, h in enumerate(headers):
            self.column_names[i] = h
            
        self.num_inputs = len(headers)
        
        # Populate the sweeps list
        for i, block in enumerate(sweep_blocks):
            arr = np.array(block, dtype=np.float64)
            self.sweeps.append(CSVSweep(arr, name=f"Sweep {i}"))
            self.num_points += arr.shape[0]
            
        self.num_sweeps = len(self.sweeps)
        
        # Keep a flat version of the data for legacy operations
        if self.num_sweeps > 0:
            self.data = np.vstack([s.data for s in self.sweeps])
        else:
            self.data = np.array([])


class DataLoaderThread(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, filename, opts):
        super().__init__()
        self.filename = filename
        self.opts = opts

    def run(self):
        try:
            self.progress.emit(10, "Initializing...")
            
            opts_type = self.opts.get("type", "BadgerLoop")
            
            if opts_type in ["CSV", "ConcatenatedCSV"]:
                self.progress.emit(30, "Parsing CSV file and detecting sweeps...")
                ds = CSVDataset(
                    self.filename, 
                    self.opts.get("delimiter", ","), 
                    self.opts.get("has_header", True)
                )
                
            elif opts_type == "MultiCSV":
                self.progress.emit(30, "Stitching CSV files into memory...")
                file_list = self.opts.get("file_list", [])
                if not file_list:
                    raise ValueError("No file list provided for folder parsing.")
                ds = MultiCSVDataset(
                    self.filename, 
                    file_list, 
                    self.opts.get("delimiter", ","), 
                    self.opts.get("has_header", True)
                )
                
            # --- NEW: HDF5 ROUTING ---
            elif opts_type == "HDF5":
                self.progress.emit(30, "Parsing HDF5 binary...")
                ds = HDF5Dataset(self.filename, self.progress.emit)
            # -------------------------
                
            else:
                self.progress.emit(30, "Parsing BadgerLoop binary...")
                ds = Dataset(self.filename) 
                
            self.progress.emit(100, "Load complete.")
            self.finished.emit(ds)
            
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            self.error.emit(str(e))


class HDF5Dataset:
    def __init__(self, fname, progress_callback=None):
        self.filename = fname
        self.column_names = {}
        self.notes = ""
        self.sweeps = []
        
        if progress_callback:
            progress_callback(10, "Opening HDF5 File...")
            
        with h5py.File(fname, 'r') as f:
            # 1. Extract Global Metadata (Attributes)
            notes_list = []
            for key, val in f.attrs.items():
                notes_list.append(f"{key}: {val}")
            self.notes = "\n".join(notes_list)
            
            # 2. Intelligently discover groups and datasets
            sweep_dict = {} 
            
            def find_datasets(name, obj):
                if isinstance(obj, h5py.Dataset) and obj.ndim == 1:
                    # Get the parent folder name (or '/' if it's at the root)
                    parent = obj.parent.name
                    if parent not in sweep_dict:
                        sweep_dict[parent] = {}
                    # Load the binary array directly into RAM
                    sweep_dict[parent][name.split('/')[-1]] = obj[:] 
                    
            f.visititems(find_datasets)
            
            if not sweep_dict:
                raise ValueError("No 1D data arrays found in this HDF5 file.")
                
            if progress_callback:
                progress_callback(50, "Formatting Sweeps...")
                
            # 3. Use the first group to establish the column names
            first_group = list(sweep_dict.keys())[0]
            col_keys = list(sweep_dict[first_group].keys())
            for i, col_name in enumerate(col_keys):
                self.column_names[i] = col_name
                
            # 4. Build a CSVSweep object for each HDF5 Group
            self.num_points = 0
            for i, (path, col_data) in enumerate(sweep_dict.items()):
                length = len(col_data[col_keys[0]])
                matrix = np.zeros((length, len(col_keys)), dtype=np.float64)
                
                for col_idx, key in enumerate(col_keys):
                    if key in col_data:
                        matrix[:, col_idx] = col_data[key]
                        
                sweep_name = path.strip('/') if path != '/' else f"Sweep {i}"
                from core.data_loader import CSVSweep # Ensure we use the container
                self.sweeps.append(CSVSweep(matrix, name=sweep_name))
                self.num_points += length
                
        self.num_sweeps = len(self.sweeps)
        if self.num_sweeps > 0:
            self.data = self.sweeps[0].data # Fallback for legacy 1D operations
            
        self.num_inputs = len(self.column_names)
        self.num_outputs = 0
        self.name = os.path.basename(fname)
        
        if progress_callback:
            progress_callback(100, "Done")
