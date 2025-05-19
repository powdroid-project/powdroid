from tkinter import ttk
import os
import sys
import webbrowser

def setup_sidebar(app, pages, show_page):
    sidebar = ttk.Frame(app, width=180, style="secondary.TFrame")
    sidebar.pack(side="left", fill="y")

    ttk.Label(sidebar, text="PowDroid", font=("Segoe UI", 16, "bold")).pack(pady=(20, 10))

    def go_home():
        show_page(pages, "home")

    def go_data_session():
        show_page(pages, "data_session")

    def go_upload_data():
        show_page(pages, "upload_data")
    
    def go_about_us():
        show_page(pages, "about_us")

    ttk.Button(sidebar, text="Home", style="primary.TButton", takefocus=0, command=go_home).pack(fill="x", padx=10, pady=5)
    ttk.Button(sidebar, text="Data Session", style="primary.TButton", takefocus=0, command=go_data_session).pack(fill="x", padx=10, pady=5)
    ttk.Button(sidebar, text="Upload Data", style="primary.TButton", takefocus=0, command=go_upload_data).pack(fill="x", padx=10, pady=5)

    sep = ttk.Separator(sidebar, orient="horizontal")
    sep.pack(fill="x", padx=sidebar.winfo_reqwidth() * 0.1, pady=10)
    sep.configure(style="White.TSeparator")

    def open_help():
        webbrowser.open("https://github.com/powdroid-project/powdroid")

    def open_issues():
        webbrowser.open("https://github.com/powdroid-project/powdroid/issues")

    ttk.Button(sidebar, text="Help", style="primary.TButton", takefocus=0, command=open_help).pack(fill="x", padx=10, pady=5)
    ttk.Button(sidebar, text="Report Issue", style="primary.TButton", takefocus=0, command=open_issues).pack(fill="x", padx=10, pady=5)

    def go_about_us():
        show_page(pages, "about_us")

    ttk.Button(sidebar, text="About Us", style="primary.TButton", takefocus=0, command=go_about_us).pack(fill="x", padx=10, pady=5)

    sep = ttk.Separator(sidebar, orient="horizontal")
    sep.pack(fill="x", padx=sidebar.winfo_reqwidth() * 0.1, pady=10)
    sep.configure(style="White.TSeparator")

    def on_restart():
        app.destroy()
        os.execl(sys.executable, sys.executable, *sys.argv)

    ttk.Button(sidebar, text="Restart", style="primary.TButton", takefocus=0, command=on_restart).pack(fill="x", padx=10, pady=5)

    def on_exit():
        app.destroy()

    ttk.Button(sidebar, text="Exit", style="primary.TButton", takefocus=0, command=on_exit).pack(fill="x", padx=10, pady=5)
