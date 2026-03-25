# core/file_editor.py
import os
import csv
import io
import re
import numpy as np

class FileEditor:
    @staticmethod
    def write_csv_mirror_from_existing(src, dest):
        with open(src, 'r', encoding='utf-8-sig', errors='ignore') as f:
            lines = f.readlines()
        has_flag = any(re.search(r'(?i)Is\s+Mirror\s+File\s*:\s*Yes', l) for l in lines[:15])
        with open(dest, 'w', encoding='utf-8-sig', newline='') as f:
            if not has_flag: f.write("# Is Mirror File: Yes\n")
            f.writelines(lines)

    @staticmethod
    def write_csv_mirror(dataset, filepath):
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            if hasattr(dataset, 'notes') and dataset.notes:
                for line in dataset.notes.split('\n'):
                    clean_line = line.lstrip('#').strip()
                    if clean_line: f.write(f"#{clean_line}\n")

            if not hasattr(dataset, 'notes') or "Is Mirror File: Yes" not in getattr(dataset, 'notes', ''):
                f.write("# Is Mirror File: Yes\n")

            writer = csv.writer(f, delimiter=',')
            headers = [dataset.column_names.get(i, f"Column {i}") for i in range(dataset.num_inputs)]
            writer.writerow(headers)

            if hasattr(dataset, 'data') and dataset.data is not None:
                for row in dataset.data:
                    clean_row = ["NaN" if np.isnan(val) else f"{val:.6g}" for val in row]
                    writer.writerow(clean_row)

    @staticmethod
    def append_column_to_file(file_type, dataset, target_file, new_name, calculated_blocks, last_load_opts):
        # --- FIXED: NATIVE HDF5 INTERCEPT ---
        if file_type == "HDF5":
            import h5py
            if hasattr(dataset, 'file') and dataset.file:
                try: dataset.file.close() # Free the Windows file lock
                except: pass
            with h5py.File(target_file, 'a') as f:
                groups = [k for k in f.keys() if isinstance(f[k], h5py.Group)]
                
                if not groups:
                    # Flat file structure (No Sweeps)
                    if new_name in f: del f[new_name]
                    data_to_write = np.concatenate(calculated_blocks) if len(calculated_blocks) > 1 else calculated_blocks[0]
                    f.create_dataset(new_name, data=data_to_write)
                else:
                    # Multi-sweep structure
                    groups.sort() # Ensure Sweep_0, Sweep_1 order matches calculated_blocks
                    for idx, grp_name in enumerate(groups):
                        if idx < len(calculated_blocks):
                            grp = f[grp_name]
                            if new_name in grp: del grp[new_name]
                            grp.create_dataset(new_name, data=calculated_blocks[idx])
            return
        # ----------------------------------

        if file_type == "MultiCSV":
            delim = last_load_opts.get("delimiter", ",")
            if delim == "auto": delim = ","

            for sw_idx, filepath in enumerate(dataset.file_list):
                with open(filepath, "r", encoding='utf-8-sig', errors='ignore') as f:
                    lines = f.readlines()

                out = []
                data_row_idx = 0
                flat_calc = calculated_blocks[sw_idx]

                has_mirror_flag = any(re.search(r'(?i)Is\s+Mirror\s+File\s*:\s*Yes', l) for l in lines[:15])
                if not has_mirror_flag:
                    out.append("# Is Mirror File: Yes\n")

                header_done = False
                for line in lines:
                    clean_line = line.rstrip('\r\n')
                    if not clean_line or clean_line.startswith('#'):
                        out.append(line)
                        continue

                    if not header_done:
                        out.append(f"{clean_line}{delim}{new_name}\n")
                        header_done = True
                    else:
                        val = flat_calc[data_row_idx] if data_row_idx < len(flat_calc) else np.nan
                        data_row_idx += 1

                        val_str = "NaN" if np.isnan(val) else f"{val:.6g}"
                        out.append(f"{clean_line}{delim}{val_str}\n")

                with open(filepath, "w", encoding='utf-8-sig') as f:
                    f.writelines(out)

        elif file_type in ["CSV", "ConcatenatedCSV"]:
            delim = last_load_opts.get("delimiter", ",")
            if delim == "auto": delim = ","

            with open(target_file, "r", encoding='utf-8-sig', errors='ignore') as f:
                lines = f.readlines()

            out = []
            has_mirror_flag = any(re.search(r'(?i)Is\s+Mirror\s+File\s*:\s*Yes', l) for l in lines[:15])
            if not has_mirror_flag:
                out.append("# Is Mirror File: Yes\n")

            header_done = False

            # Setup tracker for concatenated blocks
            sweep_idx = 0
            data_row_idx = 0
            flat_calc = calculated_blocks[0] if calculated_blocks else []

            for line in lines:
                clean_line = line.rstrip('\r\n')
                if not clean_line or clean_line.startswith('#'):
                    out.append(line)
                    # --- Shift blocks when passing a sweep divider ---
                    if "--- Sweep" in clean_line and file_type == "ConcatenatedCSV":
                        match = re.search(r'--- Sweep (\d+)', clean_line)
                        if match:
                            sweep_idx = int(match.group(1))
                            if sweep_idx < len(calculated_blocks):
                                flat_calc = calculated_blocks[sweep_idx]
                                data_row_idx = 0
                    continue

                if not header_done:
                    out.append(f"{clean_line}{delim}{new_name}\n")
                    header_done = True
                else:
                    val = flat_calc[data_row_idx] if data_row_idx < len(flat_calc) else np.nan
                    data_row_idx += 1

                    val_str = "NaN" if np.isnan(val) else f"{val:.6g}"
                    out.append(f"{clean_line}{delim}{val_str}\n")

            with open(target_file, "w", encoding='utf-8-sig') as f:
                f.writelines(out)

        else:
            num_out = getattr(dataset, 'num_outputs', 0)
            num_inp = getattr(dataset, 'num_inputs', 0)
            target_col_idx = num_out
            target_base_name = os.path.splitext(os.path.basename(target_file))[0]

            with open(target_file, "r", encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            has_outputs = False
            for i in range(len(lines)):
                if lines[i].startswith("###"): break
                match = re.search(r'(?i)^\s*outputs?[\s:=]+(\d+)', lines[i])
                if match:
                    num = int(match.group(1))
                    prefix = lines[i][:match.start(1)]
                    suffix = lines[i][match.end(1):]
                    lines[i] = f"{prefix}{num + 1}{suffix}"
                    has_outputs = True
                    break

            if not has_outputs:
                lines.insert(1, "Outputs: 1\n")

            out = []
            sweep_idx = 0
            point_idx = 0
            in_data = False
            has_outputs_section = False
            in_outputs_block = False

            has_mirror_flag = any(re.search(r'(?i)Is\s+Mirror\s+File\s*:\s*Yes', l) for l in lines)
            flag_injected = False

            for line in lines:
                if re.match(r'(?i)^Name\s*:', line):
                    out.append(f"Name: {target_base_name}\n")
                    continue

                if line.startswith("###NOTES"):
                    out.append(line)
                    if not has_mirror_flag:
                        out.append("Is Mirror File: Yes\n")
                        flag_injected = True
                    continue

                if line.startswith("###DISABLED") or line.startswith("###OUTPUTS") or line.startswith("###INPUTS") or (line.startswith("###DATA") and not line.startswith("###DATA SET")):
                    if not has_mirror_flag and not flag_injected:
                        out.append("###NOTES###\nIs Mirror File: Yes\n\n")
                        flag_injected = True

                if in_outputs_block and line.startswith("###"):
                    out.append(f"{new_name}\tBadgerLoop.CalculatedColumn\n")
                    in_outputs_block = False

                if line.startswith("###OUTPUTS"):
                    has_outputs_section = True
                    in_outputs_block = True
                    out.append(line)
                    continue

                if line.startswith("###INPUTS") or (line.startswith("###DATA") and not line.startswith("###DATA SET")):
                    if not has_outputs_section:
                        out.append("###OUTPUTS###\n")
                        out.append(f"{new_name}\tBadgerLoop.CalculatedColumn\n")
                        has_outputs_section = True

                    if line.startswith("###DATA") and not line.startswith("###DATA SET"):
                        in_data = True
                        out.append(line)
                        continue

                if in_outputs_block and not line.strip(): continue

                if in_data:
                    clean_line = line.rstrip('\r\n')
                    if '\t' in clean_line:
                        if sweep_idx < len(calculated_blocks) and point_idx >= len(calculated_blocks[sweep_idx]):
                            sweep_idx += 1
                            point_idx = 0

                        if sweep_idx < len(calculated_blocks) and point_idx < len(calculated_blocks[sweep_idx]):
                            val = calculated_blocks[sweep_idx][point_idx]
                            point_idx += 1
                        else:
                            val = np.nan

                        parts = [p for p in clean_line.split('\t') if p.strip() != ""]
                        val_str = "NaN" if np.isnan(val) else f"{val:.6g}"

                        if target_col_idx < len(parts):
                            parts.insert(target_col_idx, val_str)
                        else:
                            parts.append(val_str)

                        out.append("\t".join(parts) + "\n")
                    else:
                        out.append(line)
                else:
                    out.append(line)

            with open(target_file, "w", encoding='utf-8') as f:
                f.writelines(out)

    @staticmethod
    def rewrite_column_name_in_file(file_type, dataset, target_file, col_idx, new_name, last_load_opts):
        # --- FIXED: NATIVE HDF5 INTERCEPT ---
        if file_type == "HDF5":
            import h5py
            if hasattr(dataset, 'file') and dataset.file:
                try: dataset.file.close()
                except: pass
            with h5py.File(target_file, 'a') as f:
                old_name = dataset.column_names.get(col_idx)
                if not old_name: return
                
                groups = [k for k in f.keys() if isinstance(f[k], h5py.Group)]
                if not groups:
                    if old_name in f:
                        f[new_name] = f[old_name]
                        del f[old_name]
                else:
                    for grp_name in groups:
                        grp = f[grp_name]
                        if old_name in grp:
                            grp[new_name] = grp[old_name]
                            del grp[old_name]
            return
        # ----------------------------------

        if file_type == "MultiCSV":
            delim = last_load_opts.get("delimiter", ",")
            if delim == "auto": delim = ","

            for filepath in dataset.file_list:
                with open(filepath, "r", encoding='utf-8-sig', errors='ignore') as f:
                    lines = [l.rstrip('\r\n') for l in f.readlines()]
                if not lines: continue

                has_mirror_flag = any(re.search(r'(?i)Is\s+Mirror\s+File\s*:\s*Yes', l) for l in lines[:15])
                if not has_mirror_flag:
                    lines.insert(0, "# Is Mirror File: Yes")

                header_idx = 0
                for i, line in enumerate(lines):
                    if line.strip() and not line.strip().startswith('#'):
                        header_idx = i
                        break

                reader = csv.reader([lines[header_idx]], delimiter=delim)
                try: headers = next(reader)
                except StopIteration: continue

                if col_idx < len(headers):
                    headers[col_idx] = new_name

                out_buf = io.StringIO()
                csv.writer(out_buf, delimiter=delim).writerow(headers)
                lines[header_idx] = out_buf.getvalue().strip()

                with open(filepath, "w", encoding='utf-8') as f:
                    f.write("\n".join(lines) + "\n")

        elif file_type in ["CSV", "ConcatenatedCSV"]:
            delim = last_load_opts.get("delimiter", ",")
            if delim == "auto": delim = ","

            with open(target_file, "r", encoding='utf-8-sig', errors='ignore') as f:
                lines = [l.rstrip('\r\n') for l in f.readlines()]
            if not lines: return

            has_mirror_flag = any(re.search(r'(?i)Is\s+Mirror\s+File\s*:\s*Yes', l) for l in lines[:15])
            if not has_mirror_flag:
                lines.insert(0, "# Is Mirror File: Yes")

            header_idx = 0
            for i, line in enumerate(lines):
                if line.strip() and not line.strip().startswith('#'):
                    header_idx = i
                    break

            reader = csv.reader([lines[header_idx]], delimiter=delim)
            try: headers = next(reader)
            except StopIteration: return

            if col_idx < len(headers):
                headers[col_idx] = new_name

            out_buf = io.StringIO()
            csv.writer(out_buf, delimiter=delim).writerow(headers)
            lines[header_idx] = out_buf.getvalue().strip()

            with open(target_file, "w", encoding='utf-8') as f:
                f.write("\n".join(lines) + "\n")

        else:
            num_out = getattr(dataset, 'num_outputs', 0)
            num_inp = getattr(dataset, 'num_inputs', 0)
            has_time = (len(dataset.column_names) > num_out + num_inp)

            inst_idx = col_idx - 1 if has_time else col_idx
            enabled_names = [inst["name"] for inst in dataset.outputs] + [inst["name"] for inst in dataset.inputs]
            target_old_name = enabled_names[inst_idx] if 0 <= inst_idx < len(enabled_names) else None

            with open(target_file, "r", encoding='utf-8-sig', errors='ignore') as f:
                lines = [l.rstrip('\r\n') for l in f.readlines()]

            out = []
            in_outputs = False
            in_inputs = False

            target_base_name = os.path.splitext(os.path.basename(target_file))[0]
            has_mirror_flag = any(re.search(r'(?i)Is\s+Mirror\s+File\s*:\s*Yes', l) for l in lines)
            flag_injected = False

            for line in lines:
                if re.match(r'(?i)^Name\s*:', line):
                    out.append(f"Name: {target_base_name}")
                    continue

                if line.startswith("###DISABLED") or line.startswith("###OUTPUTS") or line.startswith("###INPUTS") or (line.startswith("###DATA") and not line.startswith("###DATA SET")):
                    if not has_mirror_flag and not flag_injected:
                        out.append("###NOTES###")
                        out.append("Is Mirror File: Yes")
                        out.append("")
                        flag_injected = True

                if line.startswith("###OUTPUTS"):
                    in_outputs = True; in_inputs = False
                    out.append(line); continue
                if line.startswith("###INPUTS"):
                    in_inputs = True; in_outputs = False
                    out.append(line); continue
                if line.startswith("###DATA"):
                    in_outputs = False; in_inputs = False
                    out.append(line); continue

                if (in_outputs or in_inputs) and line.strip():
                    parts = line.split("\t", 1)
                    if target_old_name and parts[0].strip() == target_old_name.strip():
                        parts[0] = new_name
                        line = parts[0] + ("\t" + parts[1] if len(parts) > 1 else "")

                out.append(line)

            with open(target_file, "w", encoding='utf-8') as f:
                f.write("\n".join(out) + "\n")

    @staticmethod
    def delete_column_in_file(file_type, dataset, target_file, col_idx, last_load_opts):
        # --- FIXED: NATIVE HDF5 INTERCEPT ---
        if file_type == "HDF5":
            import h5py
            if hasattr(dataset, 'file') and dataset.file:
                try: dataset.file.close()
                except: pass
            with h5py.File(target_file, 'a') as f:
                col_name = dataset.column_names.get(col_idx)
                if not col_name: return
                
                groups = [k for k in f.keys() if isinstance(f[k], h5py.Group)]
                if not groups:
                    if col_name in f: del f[col_name]
                else:
                    for grp_name in groups:
                        grp = f[grp_name]
                        if col_name in grp: del grp[col_name]
            return
        # ----------------------------------

        if file_type == "MultiCSV":
            delim = last_load_opts.get("delimiter", ",")
            if delim == "auto": delim = ","

            for filepath in dataset.file_list:
                with open(filepath, "r", encoding='utf-8-sig', errors='ignore') as f:
                    lines = [l.rstrip('\r\n') for l in f.readlines()]
                if not lines: continue

                out = []
                has_mirror_flag = any(re.search(r'(?i)Is\s+Mirror\s+File\s*:\s*Yes', l) for l in lines[:15])
                if not has_mirror_flag:
                    out.append("# Is Mirror File: Yes")

                for line in lines:
                    if line.startswith('#') or not line.strip():
                        out.append(line)
                        continue

                    parts = next(csv.reader([line], delimiter=delim))
                    if col_idx < len(parts):
                        parts.pop(col_idx)

                    temp = io.StringIO()
                    csv.writer(temp, delimiter=delim).writerow(parts)
                    out.append(temp.getvalue().strip())

                with open(filepath, "w", encoding='utf-8-sig') as f:
                    f.write("\n".join(out) + "\n")

        elif file_type in ["CSV", "ConcatenatedCSV"]:
            delim = last_load_opts.get("delimiter", ",")
            if delim == "auto": delim = ","

            with open(target_file, "r", encoding='utf-8-sig', errors='ignore') as f:
                lines = [l.rstrip('\r\n') for l in f.readlines()]
            if not lines: return

            out = []
            has_mirror_flag = any(re.search(r'(?i)Is\s+Mirror\s+File\s*:\s*Yes', l) for l in lines[:15])
            if not has_mirror_flag:
                out.append("# Is Mirror File: Yes\n")

            for line in lines:
                if line.startswith('#') or not line.strip():
                    out.append(line)
                    continue

                parts = next(csv.reader([line], delimiter=delim))
                if col_idx < len(parts):
                    parts.pop(col_idx)

                temp = io.StringIO()
                csv.writer(temp, delimiter=delim).writerow(parts)
                out.append(temp.getvalue().strip())

            with open(target_file, "w", encoding='utf-8-sig') as f:
                f.write("\n".join(out) + "\n")

        else:
            num_out = getattr(dataset, 'num_outputs', 0)
            num_inp = getattr(dataset, 'num_inputs', 0)
            has_time = (len(dataset.column_names) > num_out + num_inp)

            inst_idx = col_idx - 1 if has_time else col_idx
            is_time = (inst_idx < 0)
            is_output = (0 <= inst_idx < num_out)

            enabled_names = [inst["name"] for inst in dataset.outputs] + [inst["name"] for inst in dataset.inputs]
            target_name = None
            if not is_time and 0 <= inst_idx < len(enabled_names):
                target_name = enabled_names[inst_idx]

            outputs_left = max(0, num_out - 1) if (not is_time and is_output) else num_out
            inputs_left = max(0, num_inp - 1) if (not is_time and not is_output) else num_inp

            with open(target_file, "r", encoding='utf-8-sig', errors='ignore') as f:
                lines = [l.rstrip('\r\n') for l in f.readlines()]

            out = []
            in_outputs = False
            in_inputs = False
            in_data = False

            target_base_name = os.path.splitext(os.path.basename(target_file))[0]
            has_mirror_flag = any(re.search(r'(?i)Is\s+Mirror\s+File\s*:\s*Yes', l) for l in lines)
            flag_injected = False

            for line in lines:
                if re.match(r'(?i)^Name\s*:', line):
                    out.append(f"Name: {target_base_name}")
                    continue

                if line.startswith("###DISABLED") or line.startswith("###OUTPUTS") or line.startswith("###INPUTS") or (line.startswith("###DATA") and not line.startswith("###DATA SET")):
                    if not has_mirror_flag and not flag_injected:
                        out.append("###NOTES###")
                        out.append("Is Mirror File: Yes")
                        out.append("")
                        flag_injected = True

                if not is_time:
                    if is_output and re.match(r'(?i)^\s*outputs?[\s:=]+(\d+)', line):
                        out.append(re.sub(r'(\d+)', str(outputs_left), line, count=1))
                        continue
                    if not is_output and re.match(r'(?i)^\s*inputs?[\s:=]+(\d+)', line):
                        out.append(re.sub(r'(\d+)', str(inputs_left), line, count=1))
                        continue

                if line.startswith("###OUTPUTS"):
                    in_outputs = True; in_inputs = False; in_data = False
                    out.append(line); continue
                if line.startswith("###INPUTS"):
                    in_inputs = True; in_outputs = False; in_data = False
                    out.append(line); continue
                if line.startswith("###DATA") and not line.startswith("###DATA SET"):
                    in_data = True; in_outputs = False; in_inputs = False
                    out.append(line); continue

                if (in_outputs or in_inputs) and line.strip() and target_name:
                    parts = line.split("\t", 1)
                    if parts[0].strip() == target_name.strip():
                        continue 

                if in_data and line.strip() and not line.startswith("###"):
                    if ':' in line and '\t' not in line:
                        out.append(line)
                        continue

                    parts = line.split('\t')
                    if col_idx < len(parts):
                        parts.pop(col_idx)
                    out.append("\t".join(parts))
                    continue

                out.append(line)

            with open(target_file, "w", encoding='utf-8') as f:
                f.write("\n".join(out) + "\n")
