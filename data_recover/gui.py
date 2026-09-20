"""Simple, dependency-free graphical interface for data-recover.

Built with Tkinter (ships with Python on Windows/Mac; on some Linux
distros you may need `sudo apt install python3-tk`). Sits directly on
top of the same core engine the CLI uses (carve.py, filesystems/fat.py,
filesystems/ntfs.py). No logic is duplicated here; this is purely a
front end.
"""

from __future__ import annotations

import dataclasses
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .carve import carve_candidates_fh, scan_headers_fh
from .detect import find_filesystem
from .filesystems import fat, ntfs
from .i18n import LANGUAGES, get_language, set_language, t
from .signatures import SIGNATURES
from .utils import estimate_remaining, get_source_size, human_size, list_block_devices, iter_mounted_volumes, open_source

APP_BRAND = "FMJ Software"


def _asset_path(name: str) -> str:
    """Resolve a path under data_recover/assets/, working both when run
    from source and when frozen into a PyInstaller --onefile exe (which
    unpacks bundled data files into a temp dir at sys._MEIPASS).
    """
    base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(base, "data_recover", "assets", name)
    return os.path.join(base, "assets", name)


class DataRecoverGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Data Recover")
        self.root.geometry("780x600")
        self.root.minsize(680, 500)

        self.log_queue: "queue.Queue" = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.cancel_requested = False
        self._scan_start_time: float | None = None
        self._logo_img = None  # keep a reference so Tk doesn't garbage-collect it

        self._set_window_icon()
        self._build_widgets()
        self.root.after(100, self._drain_log_queue)

    def _set_window_icon(self):
        # This is the *app's own* icon (title bar / taskbar / exe file
        # icon), deliberately a different glyph from logo.png, which is
        # the FMJ Software company brand mark used in the header row and
        # the About dialog. .ico first: that's what Windows actually
        # uses for the title-bar icon *and* the taskbar icon (multi-
        # resolution, native format). iconphoto's PNG works everywhere
        # but on Windows the taskbar in particular is more reliable with
        # a real .ico.
        try:
            self.root.iconbitmap(default=_asset_path("app_icon.ico"))
            return
        except Exception:
            pass  # not on Windows, or .ico missing; fall through to PNG
        try:
            icon = tk.PhotoImage(file=_asset_path("app_icon.png"))
            self.root.iconphoto(True, icon)
            self._icon_img = icon  # keep reference
        except Exception:
            pass  # cosmetic only; a missing or bad asset must not break the app

    @staticmethod
    def _draw_pill_button(parent, text, command, accent, bg, width=92, height=34, radius=8):
        """A rounded-rectangle button drawn on a Canvas, because plain tk.Button
        can't do rounded corners/colored borders portably, and the flat
        text-link look didn't match the reference "OK" button style.
        """
        canvas = tk.Canvas(parent, width=width, height=height, bg=bg, highlightthickness=0, cursor="hand2")
        x1, y1, x2, y2 = 1, 1, width - 1, height - 1
        points = [
            x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
            x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
            x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
        ]
        canvas.create_polygon(points, smooth=True, outline=accent, fill=bg, width=1.5)
        canvas.create_text(width // 2, height // 2, text=text, fill=accent, font=("TkDefaultFont", 10, "bold"))
        canvas.bind("<Button-1>", lambda e: command())
        return canvas

    def _show_about(self):
        ACCENT = "#5b4fe0"
        BG = "#1e1e1e"
        BODY_FG = "#e8e8e8"
        MUTED = "#9a9a9a"
        FAINT = "#6b6b6b"

        dlg = tk.Toplevel(self.root)
        dlg.overrideredirect(True)
        dlg.configure(bg=BG)
        dlg.resizable(False, False)

        # custom header bar (there is no native title bar) with title and close "x"
        header = tk.Frame(dlg, bg=ACCENT, height=42)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text=t("about_title"), bg=ACCENT, fg="white", font=("TkDefaultFont", 10, "bold")).pack(
            side="left", padx=16
        )
        def _close(event=None):
            try:
                dlg.grab_release()
            except Exception:
                pass
            dlg.destroy()

        close_lbl = tk.Label(header, text="✕", bg=ACCENT, fg="white", font=("TkDefaultFont", 13), cursor="hand2")
        close_lbl.pack(side="right", padx=16)
        close_lbl.bind("<Button-1>", _close)

        body = tk.Frame(dlg, bg=BG)
        body.pack(fill="both", expand=True, padx=22, pady=14)

        top_row = tk.Frame(body, bg=BG)
        top_row.pack(fill="x", anchor="w")
        try:
            about_logo = tk.PhotoImage(file=_asset_path("logo.png"))
            factor = max(1, about_logo.width() // 56)
            about_logo = about_logo.subsample(factor, factor)
            self._about_logo_img = about_logo  # keep reference
            tk.Label(top_row, image=about_logo, bg=BG).pack(side="left", padx=(0, 14), anchor="n")
        except Exception:
            pass

        text_col = tk.Frame(top_row, bg=BG)
        text_col.pack(side="left", fill="both", expand=True)
        tk.Label(text_col, text=t("about_app_name"), bg=BG, fg=ACCENT, font=("TkDefaultFont", 16, "bold")).pack(anchor="w")
        tk.Label(
            text_col,
            text=t("about_subtitle", version=__version__),
            bg=BG, fg=MUTED, font=("TkDefaultFont", 9),
        ).pack(anchor="w", pady=(2, 0))

        tk.Label(
            body, text=t("about_by", brand=APP_BRAND),
            bg=BG, fg=BODY_FG, font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w", pady=(12, 3))
        tk.Label(
            body,
            text=t("about_desc"),
            bg=BG, fg=MUTED, font=("TkDefaultFont", 9), justify="left",
        ).pack(anchor="w")

        tk.Label(body, text=t("about_tech"), bg=BG, fg=FAINT, font=("TkDefaultFont", 8)).pack(
            anchor="w", pady=(10, 0)
        )

        btn_row = tk.Frame(body, bg=BG)
        btn_row.pack(fill="x", pady=(14, 0))
        self._draw_pill_button(btn_row, t("about_ok"), _close, ACCENT, BG).pack(side="right")

        dlg.bind("<Escape>", _close)
        dlg.transient(self.root)
        dlg.update_idletasks()
        w, h = 500, dlg.winfo_reqheight()
        px, py = self.root.winfo_rootx(), self.root.winfo_rooty()
        pw, ph = self.root.winfo_width(), self.root.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        dlg.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")

        # Make sure the (frameless) window is actually mapped, raised and
        # focused before anything modal happens, because grabbing input on a
        # toplevel that never got shown/focused is what froze the app
        # (all clicks silently went to an invisible window with no way to
        # reach its close button). Deliberately left non-modal (no
        # grab_set) so a rendering hiccup on some Windows setups can never
        # lock out the main window again. Worst case the user
        # can click behind it, not that the whole app becomes unusable.
        dlg.deiconify()
        dlg.lift()
        dlg.attributes("-topmost", True)
        dlg.focus_force()
        dlg.protocol("WM_DELETE_WINDOW", _close)

    # ---------------------------------------------------------------- UI

    def _build_widgets(self):
        pad = {"padx": 8, "pady": 6}

        brand = ttk.Frame(self.root)
        brand.pack(fill="x", padx=8, pady=(8, 0))
        try:
            logo_img = tk.PhotoImage(file=_asset_path("logo.png"))
            # Downscale the source icon (roughly 512px) to a small header logo.
            factor = max(1, logo_img.width() // 40)
            logo_img = logo_img.subsample(factor, factor)
            self._logo_img = logo_img
            ttk.Label(brand, image=logo_img).pack(side="left", padx=(0, 8))
        except Exception:
            pass
        ttk.Label(brand, text=APP_BRAND, font=("TkDefaultFont", 14, "bold")).pack(side="left")
        ttk.Button(brand, text=t("brand_about_btn"), command=self._show_about).pack(side="right")

        lang_names = list(LANGUAGES.values())
        lang_codes = list(LANGUAGES.keys())
        self._lang_var = tk.StringVar(value=LANGUAGES[get_language()])
        lang_combo = ttk.Combobox(brand, textvariable=self._lang_var, values=lang_names, state="readonly", width=10)
        lang_combo.pack(side="right", padx=(0, 10))

        def _on_lang_selected(event=None):
            idx = lang_names.index(self._lang_var.get())
            self._change_language(lang_codes[idx])

        lang_combo.bind("<<ComboboxSelected>>", _on_lang_selected)
        ttk.Label(brand, text=t("language_label")).pack(side="right", padx=(0, 4))

        ttk.Separator(self.root, orient="horizontal").pack(fill="x", padx=8, pady=(6, 0))

        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)

        ttk.Label(top, text=t("source_label")).grid(row=0, column=0, sticky="w")
        self.source_var = tk.StringVar()
        source_entry = ttk.Entry(top, textvariable=self.source_var, width=60)
        source_entry.grid(row=1, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(top, text=t("browse_image_btn"), command=self._browse_image).grid(row=1, column=1)
        ttk.Button(top, text=t("list_devices_btn"), command=self._list_devices).grid(row=1, column=2)
        ttk.Button(top, text=t("list_volumes_btn"), command=self._list_volumes).grid(row=1, column=3)
        top.columnconfigure(0, weight=1)

        ttk.Label(top, text=t("output_label")).grid(row=2, column=0, sticky="w", pady=(10, 0))
        self.output_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.output_var, width=60).grid(row=3, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(top, text=t("browse_output_btn"), command=self._browse_output).grid(row=3, column=1)

        # format selection
        fmt_frame = ttk.LabelFrame(self.root, text=t("formats_frame_title"))
        fmt_frame.pack(fill="x", **pad)
        self.format_vars: dict[str, tk.BooleanVar] = {}
        cols = 6
        for i, sig in enumerate(SIGNATURES):
            key = sig.name
            if key in self.format_vars:
                continue
            var = tk.BooleanVar(value=True)
            self.format_vars[key] = var
            cb = ttk.Checkbutton(fmt_frame, text=f"{sig.name} (.{sig.ext})", variable=var)
            cb.grid(row=i // cols, column=i % cols, sticky="w", padx=4)
        btns = ttk.Frame(fmt_frame)
        btns.grid(row=(len(SIGNATURES) // cols) + 1, column=0, columnspan=cols, sticky="w", pady=(4, 0))
        ttk.Button(btns, text=t("select_all_btn"), command=lambda: self._set_all_formats(True)).pack(side="left", padx=2)
        ttk.Button(btns, text=t("select_none_btn"), command=lambda: self._set_all_formats(False)).pack(side="left", padx=2)

        # action buttons
        action_frame = ttk.Frame(self.root)
        action_frame.pack(fill="x", **pad)
        self.scan_btn = ttk.Button(action_frame, text=t("scan_btn"), command=self._start_scan)
        self.scan_btn.pack(side="left", padx=(0, 6))
        self.undelete_btn = ttk.Button(action_frame, text=t("undelete_btn"), command=self._start_undelete)
        self.undelete_btn.pack(side="left", padx=6)
        self.carve_btn = ttk.Button(action_frame, text=t("carve_btn"), command=self._start_carve)
        self.carve_btn.pack(side="left", padx=6)
        self.cancel_btn = ttk.Button(action_frame, text=t("cancel_btn"), command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="right")

        # progress
        prog_frame = ttk.Frame(self.root)
        prog_frame.pack(fill="x", **pad)
        self.progress = ttk.Progressbar(prog_frame, mode="determinate")
        self.progress.pack(fill="x")
        self.status_var = tk.StringVar(value=t("ready_status"))
        ttk.Label(prog_frame, textvariable=self.status_var).pack(anchor="w", pady=(4, 0))

        # log
        log_frame = ttk.LabelFrame(self.root, text=t("log_frame_title"))
        log_frame.pack(fill="both", expand=True, **pad)
        self.log_text = tk.Text(log_frame, height=12, state="disabled", wrap="word")
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _change_language(self, lang_code: str):
        """Switch the UI language immediately, no restart needed. Static
        labels are built once per widget in _build_widgets (plain
        ttk.Label(text=...), not a live textvariable), so the simplest
        correct way to re-translate everything is to tear the window
        down and rebuild it. State the user already entered (source/
        output paths, format checkboxes, log so far) is captured first
        and restored after.
        """
        source = self.source_var.get()
        output = self.output_var.get()
        format_state = {name: var.get() for name, var in self.format_vars.items()}
        log_content = self.log_text.get("1.0", "end-1c")

        set_language(lang_code)

        for child in list(self.root.winfo_children()):
            child.destroy()

        self._build_widgets()

        self.source_var.set(source)
        self.output_var.set(output)
        for name, value in format_state.items():
            if name in self.format_vars:
                self.format_vars[name].set(value)
        if log_content:
            self.log_text.configure(state="normal")
            self.log_text.insert("end", log_content)
            self.log_text.configure(state="disabled")

    # ------------------------------------------------------------ helpers

    def _set_all_formats(self, value: bool):
        for var in self.format_vars.values():
            var.set(value)

    def _selected_formats(self):
        selected = [name for name, var in self.format_vars.items() if var.get()]
        if len(selected) == len(self.format_vars):
            return None  # all selected == no filter
        return selected

    def _browse_image(self):
        path = filedialog.askopenfilename(title=t("dlg_pick_image_title"))
        if path:
            self.source_var.set(path)

    def _browse_output(self):
        path = filedialog.askdirectory(title=t("dlg_pick_output_title"))
        if path:
            self.output_var.set(path)

    def _list_devices(self):
        devices = list_block_devices()
        if not devices:
            messagebox.showinfo(t("devices_title"), t("devices_none_msg"))
            return
        win = tk.Toplevel(self.root)
        win.title(t("devices_found_title"))
        listbox = tk.Listbox(win, width=80)
        listbox.pack(fill="both", expand=True, padx=8, pady=8)
        for path, desc in devices:
            listbox.insert("end", f"{path}\t{desc}")

        def use_selected():
            sel = listbox.curselection()
            if sel:
                chosen = devices[sel[0]][0]
                self.source_var.set(chosen)
                win.destroy()

        ttk.Button(win, text=t("use_as_source_btn"), command=use_selected).pack(pady=(0, 8))

    def _list_volumes(self):
        volumes = iter_mounted_volumes()
        if not volumes:
            messagebox.showinfo(t("volumes_title"), t("volumes_none_msg"))
            return
        win = tk.Toplevel(self.root)
        win.title(t("volumes_found_title"))
        listbox = tk.Listbox(win, width=80)
        listbox.pack(fill="both", expand=True, padx=8, pady=8)
        for path, desc in volumes:
            listbox.insert("end", f"{path}\t{desc}")

        def use_selected():
            sel = listbox.curselection()
            if sel:
                chosen = volumes[sel[0]][0]
                self.source_var.set(chosen)
                win.destroy()

        ttk.Button(win, text=t("use_as_source_btn"), command=use_selected).pack(pady=(0, 8))

    def _log(self, msg: str):
        self.log_queue.put(msg)

    def _drain_log_queue(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log_text.configure(state="normal")
                self.log_text.insert("end", msg + "\n")
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self._drain_log_queue)

    def _validate_inputs(self) -> bool:
        source = self.source_var.get().strip()
        output = self.output_var.get().strip()
        if not source:
            messagebox.showwarning(t("missing_info_title"), t("missing_source_msg"))
            return False
        if not output:
            messagebox.showwarning(t("missing_info_title"), t("missing_output_msg"))
            return False
        if not os.path.exists(source):
            messagebox.showerror(t("source_not_found_title"), t("source_not_found_msg", source=source))
            return False
        try:
            src_real = os.path.realpath(source)
            out_real = os.path.realpath(output)
            if os.path.isdir(src_real) and (out_real == src_real or out_real.startswith(src_real + os.sep)):
                messagebox.showerror(t("warning_title"), t("output_inside_source_msg"))
                return False
        except OSError:
            pass
        return True

    def _set_running(self, running: bool):
        state = "disabled" if running else "normal"
        self.scan_btn.configure(state=state)
        self.undelete_btn.configure(state=state)
        self.carve_btn.configure(state=state)
        self.cancel_btn.configure(state=("normal" if running else "disabled"))

    def _cancel(self):
        self.cancel_requested = True
        self._log(t("cancel_requested_log"))

    # ------------------------------------------------------------ actions

    def _start_scan(self):
        self._run_in_thread(self._do_scan)

    def _start_undelete(self):
        self._run_in_thread(self._do_undelete)

    def _start_carve(self):
        self._run_in_thread(self._do_carve)

    def _run_in_thread(self, target):
        if not self._validate_inputs():
            return
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo(t("busy_title"), t("busy_msg"))
            return
        self.cancel_requested = False
        self._set_running(True)
        self.progress.configure(value=0, maximum=100)
        self._scan_start_time = time.time()
        self.worker_thread = threading.Thread(target=self._safe_run, args=(target,), daemon=True)
        self.worker_thread.start()

    def _safe_run(self, target):
        try:
            target()
        except PermissionError:
            self._log(t("permission_error_log"))
        except Exception as e:  # noqa: BLE001
            self._log(t("generic_error_log", error=e))
        finally:
            self._set_status(t("done_status"))
            self.root.after(0, lambda: self._set_running(False))

    def _set_status(self, text: str):
        # Tkinter variables must only be touched from the main thread; this
        # is called from the worker thread, so always hop back via after().
        self.root.after(0, lambda: self.status_var.set(text))

    def _progress_cb(self, done: int, total: int):
        if total:
            pct = done / total * 100
            self.root.after(0, lambda: self.progress.configure(value=pct))
        elapsed = time.time() - self._scan_start_time if self._scan_start_time else 0
        eta = estimate_remaining(done, total, elapsed)
        eta_part = t("eta_remaining", eta=eta) if eta else t("eta_calculating")
        self._set_status(f"{human_size(done)} / {human_size(total)}{eta_part}")

    def _run_undelete(self, fh):
        """Returns (kind, absolute_fat_boot, seen_dir_offsets). See the
        CLI's _do_undelete docstring for what these mean and why the
        offsets get shifted to be raw-disk-absolute. absolute_fat_boot is
        None unless a FAT filesystem was found (orphan directory-entry
        scanning isn't implemented for NTFS).
        """
        output = self.output_var.get().strip()
        view, kind, boot, part_offset = find_filesystem(fh)

        if part_offset is not None:
            self._log(t("partition_found_log", offset=part_offset))
        shift = part_offset or 0

        if kind == "ntfs":
            self._log(t("ntfs_detected_log"))
            entries = ntfs.find_deleted_entries(view, boot)
            self._log(t("deleted_found_log", count=len(entries)))
            self._scan_start_time = time.time()
            recovered = 0
            for i, e in enumerate(entries):
                if self.cancel_requested:
                    self._log(t("cancelled_log"))
                    break
                path = ntfs.recover_entry(view, boot, e, output)
                if path:
                    recovered += 1
                    self._log(t("recovered_log", name=os.path.basename(path), size=human_size(e.size)))
                self._progress_cb(i + 1, len(entries))
            self._log(t("total_recovered_log", recovered=recovered, total=len(entries)))
            return kind, None, set()

        if kind == "fat":
            self._log(t("fat_detected_log", fat_type=boot.fat_type))
            entries = fat.find_deleted_entries(view, boot)
            self._log(t("deleted_found_log", count=len(entries)))
            self._scan_start_time = time.time()
            recovered = 0
            for i, e in enumerate(entries):
                if self.cancel_requested:
                    self._log(t("cancelled_log"))
                    break
                path = fat.recover_entry(view, boot, e, output)
                if path:
                    recovered += 1
                    self._log(t("recovered_log", name=os.path.basename(path), size=human_size(e.size)))
                self._progress_cb(i + 1, len(entries))
            self._log(t("total_recovered_log", recovered=recovered, total=len(entries)))
            absolute_boot = boot if not shift else dataclasses.replace(
                boot,
                fat_start=boot.fat_start + shift,
                cluster_heap_start=boot.cluster_heap_start + shift,
            )
            seen = {e.dir_offset + shift for e in entries}
            return kind, absolute_boot, seen

        self._log(t("no_fs_found_log"))
        return kind, None, set()

    def _absolute_fat_boot(self, fh):
        # Same idea as the CLI's helper of the same name: a cheap
        # (boot-sector-only) filesystem probe so a standalone carve run
        # (not preceded by undelete) still gets orphan directory-entry
        # scanning when the source is FAT.
        try:
            _view, kind, boot, part_offset = find_filesystem(fh)
        except Exception:
            return None
        if kind != "fat" or boot is None:
            return None
        if not part_offset:
            return boot
        return dataclasses.replace(
            boot,
            fat_start=boot.fat_start + part_offset,
            cluster_heap_start=boot.cluster_heap_start + part_offset,
        )

    def _run_carve(self, fh, total_size, boot_sector=None, seen_dir_offsets=None):
        output = self.output_var.get().strip()
        formats = self._selected_formats()

        if boot_sector is None:
            boot_sector = self._absolute_fat_boot(fh)
            if boot_sector:
                self._log(t("fat_trace_log"))

        orphan_entries = [] if boot_sector else None
        self._set_status(t("scanning_status"))
        self._scan_start_time = time.time()
        candidates = scan_headers_fh(
            fh,
            total_size,
            formats=formats,
            progress_cb=self._progress_cb,
            boot_sector=boot_sector,
            orphan_sink=orphan_entries,
        )
        self._log(t("candidates_found_log", count=len(candidates)))

        if orphan_entries:
            seen = seen_dir_offsets or set()
            new_entries = [e for e in orphan_entries if e.dir_offset not in seen]
            self._log(t("orphan_found_log", count=len(orphan_entries), new=len(new_entries)))
            named_recovered = 0
            for e in new_entries:
                if self.cancel_requested:
                    break
                path = fat.recover_entry(fh, boot_sector, e, output)
                if path:
                    named_recovered += 1
                    self._log(t("orphan_recovered_log", name=os.path.basename(path), size=human_size(e.size)))
            self._log(t("orphan_total_log", recovered=named_recovered, total=len(new_entries)))

        if not candidates or self.cancel_requested:
            return
        self._set_status(t("extracting_status"))
        self._scan_start_time = time.time()
        recovered = carve_candidates_fh(fh, total_size, candidates, output, progress_cb=self._progress_cb)
        by_format: dict[str, list] = {}
        for r in recovered:
            by_format.setdefault(r.format, [0, 0])
            by_format[r.format][0] += 1
            by_format[r.format][1] += r.size
        self._log(t("total_files_log", count=len(recovered)))
        for fmt, (count, total_size_fmt) in sorted(by_format.items()):
            self._log(t("format_count_log", fmt=fmt, count=count, size=human_size(total_size_fmt)))
        truncated = sum(1 for r in recovered if r.truncated)
        if truncated:
            self._log(t("truncated_note_log", count=truncated))

    def _do_undelete(self):
        source = self.source_var.get().strip()
        self._log(t("fs_scan_header_log", source=source))
        with open_source(source) as fh:
            self._run_undelete(fh)

    def _do_carve(self):
        source = self.source_var.get().strip()
        self._log(t("sig_scan_header_log", source=source))
        with open_source(source) as fh:
            total_size = get_source_size(source, fh)
            self._run_carve(fh, total_size)

    def _do_scan(self):
        # Opens the source ONCE and reuses the same handle for both
        # phases. Closing a raw Windows device handle and immediately
        # reopening it can spuriously fail (observed in practice), so
        # undelete and carve must share one handle here rather than each
        # doing their own open/close.
        source = self.source_var.get().strip()
        with open_source(source) as fh:
            total_size = get_source_size(source, fh)
            self._log(t("fs_scan_header_log", source=source))
            kind, absolute_boot, seen_dir_offsets = self._run_undelete(fh)
            if not self.cancel_requested:
                self._log("")
                self._log(t("sig_scan_header_log", source=source))
                self._run_carve(fh, total_size, boot_sector=absolute_boot, seen_dir_offsets=seen_dir_offsets)


def main():
    root = tk.Tk()
    try:
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:
        pass
    app = DataRecoverGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
