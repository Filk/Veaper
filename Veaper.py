import os
import sys
import subprocess
import threading
import traceback
import urllib.parse
import urllib.request
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


def resource_path(*parts):
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *parts)


def normalize_path(path):
    path = str(path)
    if path.startswith("file:"):
        parsed = urllib.parse.urlparse(path)
        path = urllib.request.url2pathname(parsed.path)
    return os.path.abspath(path)


def reveal_in_file_browser(path):
    if sys.platform == "darwin":
        subprocess.run(["open", "-R", path], check=False)
    elif sys.platform == "win32":
        subprocess.run(["explorer", "/select,%s" % os.path.normpath(path)], check=False)
    else:
        folder = path if os.path.isdir(path) else os.path.dirname(path)
        subprocess.run(["xdg-open", folder], check=False)


def browser_question():
    if sys.platform == "darwin":
        return "Show it in Finder?"
    if sys.platform == "win32":
        return "Show it in File Explorer?"
    return "Show the project folder?"


def run_self_check(output_path):
    lines = []
    code = 1
    try:
        from veaperProcessing import find_ffmpeg
        import aaf2

        ffmpeg = find_ffmpeg()
        lines.append("OK")
        lines.append(ffmpeg)
        lines.append(getattr(aaf2, "__file__", "aaf2"))
        code = 0
    except Exception:
        lines.append("FAIL")
        lines.append(traceback.format_exc())
        if getattr(sys, "frozen", False):
            root = getattr(sys, "_MEIPASS", "")
            lines.append("MEIPASS " + str(root))
            if root and os.path.isdir(root):
                lines.extend(sorted(os.listdir(root))[:80])
    text = "\n".join(lines) + "\n"
    if output_path:
        with open(output_path, "w") as handle:
            handle.write(text)
    else:
        sys.stdout.write(text)
    return code


class VeaperApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Veaper")
        self.minsize(560, 460)
        self.aaf_path = None
        self.project_path = None
        self._busy = False

        self.file_var = tk.StringVar(value="No file chosen yet")
        self.folder_var = tk.StringVar(value="Put the AAF and its MXF files in the same folder.")
        self.status_var = tk.StringVar(value="Choose an AAF file to begin.")

        self._build()
        self._place_on_screen()
        self._set_icon()
        self._listen_for_opened_files()
        self.after(200, self._open_paths_from_argv)

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        frame = ttk.Frame(self, padding=20)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text="Veaper", font=("Helvetica", 22, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(
            frame,
            text="Turns a DaVinci Resolve AAF into a Reaper project.",
            wraplength=500,
        ).grid(row=1, column=0, sticky="w", pady=(2, 16))

        self.choose_button = ttk.Button(frame, text="1. Choose AAF file", command=self.browse_aaf_file)
        self.choose_button.grid(row=2, column=0, sticky="ew")

        ttk.Label(frame, textvariable=self.file_var, font=("Helvetica", 13, "bold"), wraplength=500).grid(
            row=3, column=0, sticky="w", pady=(12, 0)
        )
        ttk.Label(frame, textvariable=self.folder_var, wraplength=500).grid(row=4, column=0, sticky="w", pady=(2, 12))

        ttk.Label(
            frame,
            text="Keep every MXF file in that same folder. Veaper converts the audio to WAV and writes a Reaper project next to the AAF.",
            wraplength=500,
        ).grid(row=5, column=0, sticky="w", pady=(0, 14))

        self.create_button = ttk.Button(frame, text="2. Create Reaper project", command=self.start_processing)
        self.create_button.grid(row=6, column=0, sticky="ew")
        self.create_button.state(["disabled"])

        ttk.Label(frame, textvariable=self.status_var, wraplength=500).grid(row=7, column=0, sticky="w", pady=(14, 8))

        self.show_button = ttk.Button(frame, text="Show the Reaper project", command=self.show_project)
        self.show_button.grid(row=8, column=0, sticky="ew")
        self.show_button.state(["disabled"])

        footer = ttk.Frame(frame)
        footer.grid(row=9, column=0, sticky="ew", pady=(16, 0))
        footer.columnconfigure(1, weight=1)
        ttk.Button(footer, text="Help", command=self.show_help).grid(row=0, column=0, sticky="w")
        ttk.Label(footer, text="filipelopes.net").grid(row=0, column=2, sticky="e")

        self.bind("<Return>", lambda _event: self.start_processing())

    def _place_on_screen(self):
        self.update_idletasks()
        width, height = 600, 500
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 3)
        self.geometry("%dx%d+%d+%d" % (width, height, x, y))

    def _set_icon(self):
        icon = resource_path("icons", "veaper.png")
        if not os.path.isfile(icon):
            icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "veaper.png")
        if not os.path.isfile(icon):
            return
        try:
            self._icon_image = tk.PhotoImage(file=icon)
            self.iconphoto(True, self._icon_image)
        except tk.TclError:
            pass

    def _listen_for_opened_files(self):
        try:
            self.createcommand("::tk::mac::OpenDocument", self._opened_from_finder)
        except tk.TclError:
            pass

    def _open_paths_from_argv(self):
        for arg in sys.argv[1:]:
            if arg.startswith("-"):
                continue
            path = normalize_path(arg)
            if path.lower().endswith(".aaf"):
                self.set_aaf_file(path)
                return

    def _opened_from_finder(self, *paths):
        for path in paths:
            normalized = normalize_path(path)
            if normalized.lower().endswith(".aaf"):
                self.set_aaf_file(normalized)
                return

    def browse_aaf_file(self):
        if self._busy:
            return
        file_path = filedialog.askopenfilename(
            title="Choose the AAF file",
            filetypes=[("AAF files", "*.aaf"), ("All files", "*.*")],
        )
        if file_path:
            self.set_aaf_file(file_path)

    def set_aaf_file(self, path):
        path = normalize_path(path)
        if not path.lower().endswith(".aaf") or not os.path.isfile(path):
            messagebox.showwarning("Veaper", "Please choose an AAF file.")
            return
        self.aaf_path = path
        self.project_path = None
        self.file_var.set(os.path.basename(path))
        self.folder_var.set(os.path.dirname(path))
        self.status_var.set("Ready. MXF files need to be in this same folder.")
        self.create_button.state(["!disabled"])
        self.show_button.state(["disabled"])

    def start_processing(self):
        if self._busy:
            return
        if not self.aaf_path:
            messagebox.showwarning("Veaper", "Choose an AAF file first.")
            return

        self._busy = True
        self.choose_button.state(["disabled"])
        self.create_button.state(["disabled"])
        self.show_button.state(["disabled"])
        self.status_var.set("Working... this can take a few minutes. You can leave this window open.")
        self.configure(cursor="watch")

        worker = threading.Thread(target=self._process, daemon=True)
        worker.start()

    def _process(self):
        try:
            from veaperProcessing import import_aaf

            workdir = os.path.dirname(self.aaf_path)
            os.chdir(workdir)
            result = import_aaf(
                workdir,
                self.aaf_path,
                on_status=lambda message: self.after(0, self.status_var.set, message),
            )
            self.after(0, self._finished, result)
        except Exception as exc:
            self.after(0, self._failed, exc)

    def _set_idle(self):
        self._busy = False
        self.configure(cursor="")
        self.choose_button.state(["!disabled"])
        if self.aaf_path:
            self.create_button.state(["!disabled"])

    def _finished(self, result):
        self._set_idle()
        self.project_path = result["project"]
        self.show_button.state(["!disabled"])
        self.status_var.set("Done. The Reaper project is in the same folder as the AAF, inside Reaper_from_DaVinci.")

        lines = [
            "The Reaper project is ready:",
            result["project"],
            "",
            "Open my_project.rpp in Reaper. Leave the WAV files in that folder.",
        ]
        warnings = result.get("warnings") or []
        if warnings:
            lines.extend(["", "Some files need attention:"])
            lines.extend("• %s" % warning for warning in warnings)
        lines.extend(["", browser_question()])

        if messagebox.askyesno("Veaper", "\n".join(lines)):
            reveal_in_file_browser(result["project"])

    def _failed(self, exc):
        self._set_idle()
        self.status_var.set("Something went wrong. Veaper did not finish the project.")
        messagebox.showerror("Veaper", str(exc) or "Something went wrong.")

    def show_project(self):
        if self.project_path and os.path.exists(self.project_path):
            reveal_in_file_browser(self.project_path)
        else:
            messagebox.showwarning("Veaper", "Create a Reaper project first.")

    def show_help(self):
        import webbrowser

        webbrowser.open("https://filipelopes.net/veaper")


def main():
    if "--self-check" in sys.argv:
        output_path = None
        index = sys.argv.index("--self-check")
        if index + 1 < len(sys.argv):
            output_path = sys.argv[index + 1]
        raise SystemExit(run_self_check(output_path))

    app = VeaperApp()
    app.mainloop()


if __name__ == "__main__":
    main()
