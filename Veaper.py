import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import webbrowser

from veaperProcessing import import_aaf  # This is your main processing function

ficheiroAFF = ""

class VeaperApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Veaper")
        self.geometry("700x350")
        self.configure(padx=10, pady=10)

        self.dragged_file_AAF = None
        self.create_widgets()

    def create_widgets(self):
        # Row 0
        tk.Label(self, text="Uploaded AAF file").grid(row=0, column=2, sticky="s")

        # Row 2 - AAF Drop Area
        tk.Label(self, text="1º").grid(row=1, column=0, sticky="e")
        self.drop_area_aaf = tk.Label(self, text="Click here and choose the AAF file", relief="sunken", bg="light grey", height=3, font=("Arial", 12, "bold"))
        self.drop_area_aaf.grid(row=1, column=1, sticky="nsew")
        self.drop_area_aaf.bind("<Button-1>", self.browse_aaf_file)

        self.aaf_display = tk.Listbox(self)
        self.aaf_display.grid(row=1, column=2, sticky="nsew")
        self.columnconfigure(2, weight=1)
        self.rowconfigure(1, weight=1)

        # Row 3 - Start button
        tk.Label(self, text="2º").grid(row=2, column=0, sticky="e")
        self.start_button = tk.Button(self, text="Click here to start process and wait", command=self.start_processing, bg="dark grey", fg="black", font=("Arial", 10, "normal"))
        self.start_button.grid(row=2, column=1, sticky="w", pady=10)

        # Row 5 - Status label
        self.status_label = tk.Label(self, text="")
        self.status_label.grid(row=3, column=1, columnspan=2, sticky="w")

        # Row 6 - Help and Footer
        self.help_button = tk.Button(self, text="Help", command=self.show_help)
        self.help_button.grid(row=4, column=0, sticky="s")
        tk.Label(self, text="filipelopes.net").grid(row=4, column=2, sticky="e")

    def browse_aaf_file(self, event=None):
        messagebox.showwarning("Warning", "Keep all MXF files in the same folder as the AAF file!")
        file = filedialog.askopenfilename(filetypes=[("AAF files", "*.aaf")])
        if file:
            self.dragged_file_AAF = file
            #file = caminho para o ficheiro aaf
            self.aaf_display.delete(0, tk.END)
            self.aaf_display.insert(tk.END, os.path.basename(file))
            global ficheiroAFF
            ficheiroAFF=file

    def start_processing(self):
        if not self.dragged_file_AAF:
            messagebox.showwarning("Warning", "Please select an AAF file first.")
            return

        self.status_label.config(text="Processing...please wait.")

        try:
            # Change working directory to the location of the AAF file
            workdir = os.path.dirname(self.dragged_file_AAF)
            os.chdir(workdir)

            import_aaf(workdir,ficheiroAFF)  # Call your backend processor

            self.status_label.config(text="Done! Check the AAF file folder and find the Reaper Project")
            messagebox.showinfo("Finished", "Processing completed successfully.")
        except Exception as e:
            self.status_label.config(text="Error during processing.")
            messagebox.showerror("Error", str(e))

    def show_help(self):
        webbrowser.open("https://filipelopes.net/veaper")

if __name__ == "__main__":
    app = VeaperApp()
    app.mainloop()
