# core/data_loader.py
import os
import csv
import time
import builtins
import traceback
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal

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


class CSVDataset:
    def __init__(self, fname, delimiter='auto', has_header=True, progress_callback=None):
        self.filename = fname
        self.column_names = {}
        self.num_sweeps = 1  
        self.notes = ""
        
        file_size = os.path.getsize(fname)
        notes_lines = []
        clean_lines = []
        
        # 'utf-8-sig' automatically strips the invisible Byte Order Mark (BOM)
        with open(fname, 'r', encoding='utf-8-sig', errors='ignore') as f:
            if progress_callback:
                f = TrackedFile(f, file_size, progress_callback, "Reading CSV")
                
            # Separate metadata hashtags from pure data rows
            for line in f:
                stripped = line.strip()
                if not stripped: continue
                
                if stripped.startswith('#'):
                    notes_lines.append(stripped.lstrip('#').strip())
                else:
                    clean_lines.append(line)
                    
        actual_delim = delimiter
        if delimiter == 'auto' or not delimiter:
            actual_delim = ',' # Default fallback
            try:
                sample = "".join(clean_lines[:20])
                if sample.strip():
                    sniffer = csv.Sniffer()
                    actual_delim = sniffer.sniff(sample, delimiters=',\t; |').delimiter
            except Exception:
                pass
                
        try:
            reader = csv.reader(clean_lines, delimiter=actual_delim)
            rows = list(reader)
        except Exception:
            rows = []
            
        if not rows:
            self.data = np.array([])
            self.num_points = 0
            self.num_inputs = 0
            self.num_outputs = 0
            return
            
        if has_header:
            headers = rows[0]
            data_rows = rows[1:]
            for i, h in enumerate(headers):
                self.column_names[i] = h.strip()
        else:
            data_rows = rows
            for i in range(len(rows[0])):
                self.column_names[i] = f"Column {i}"
                
        # Parse data into floats, replacing junk data with NaNs
        clean_data = []
        for row in data_rows:
            clean_row = []
            for val in row:
                try: clean_row.append(float(val))
                except ValueError: clean_row.append(np.nan)
            clean_data.append(clean_row)
            
        self.data = np.array(clean_data)
        self.num_points = len(self.data)
        self.num_inputs = len(self.column_names)
        self.num_outputs = 0
        self.date = None
        self.name = os.path.basename(fname)
        self.notes = "\n".join(notes_lines) if notes_lines else ""


class DataLoaderThread(QThread):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(int, str)

    def __init__(self, fname, opts):
        super().__init__()
        self.fname = fname
        self.opts = opts

    def run(self):
        try:
            file_size = os.path.getsize(self.fname)
            original_open = builtins.open
            
            # Monkey-patch Python's 'open' function to inject our TrackedFile safely
            def hooked_open(name, *args, **kwargs):
                f = original_open(name, *args, **kwargs)
                try:
                    if isinstance(name, (str, bytes)) and os.path.basename(self.fname) in str(name):
                        return TrackedFile(f, file_size, self.progress.emit, "Reading BadgerLoop")
                except Exception:
                    pass
                return f

            builtins.open = hooked_open
            try:
                if self.opts["type"] == "CSV":
                    # Bypass hook for CSVs, inject it directly inside CSVDataset for total safety
                    builtins.open = original_open 
                    dataset = CSVDataset(
                        self.fname, 
                        delimiter=self.opts["delimiter"], 
                        has_header=self.opts["has_header"],
                        progress_callback=self.progress.emit
                    )
                else:
                    dataset = Dataset(self.fname)
            finally:
                builtins.open = original_open 
                
            self.progress.emit(100, "File reading complete. Preparing...")
            self.finished.emit(dataset)
        except Exception as e:
            self.error.emit(str(e) + "\n" + traceback.format_exc())
