from tkinter import ttk
from tkinter import filedialog, messagebox, BooleanVar
from . import adb_runner as adb
from . import csv_handler as csv
from . import html_renderer as html

import csv as pycsv
from pathlib import Path
from datetime import datetime
from tkinter import PhotoImage

def add_footer(parent):
    copyright_label = ttk.Label(
        parent,
        text="© 2022-2025 PowDroid. All rights reserved.",
        font=("Segoe UI", 8),
        foreground="#888888"
    )
    copyright_label.pack(side="bottom", pady=(0, 5))

def create_pages(app):
    pages = {}

    # --- HOME PAGE ---
    home_page = ttk.Frame(app, style="TFrame")

    ICO_DIR = Path(__file__).resolve().parent / "../../gui/ressources"
    try:
        app.iconbitmap(ICO_DIR / "powdroid_logo.ico")
    except Exception:
        pass

    try:
        banner_path = ICO_DIR / "powdroid_banner.png"
        if banner_path.exists():
            banner_img = PhotoImage(file=str(banner_path))
            banner_label = ttk.Label(home_page, image=banner_img)
            banner_label.image = banner_img
            banner_label.pack(pady=(10, 10))
            ttk.Frame(home_page, height=20).pack()
        else:
            banner_path_ico = ICO_DIR / "powdroid_banner.ico"
            if banner_path_ico.exists():
                banner_img = PhotoImage(file=str(banner_path_ico))
                banner_label = ttk.Label(home_page, image=banner_img)
                banner_label.image = banner_img
                banner_label.pack(pady=(10, 10))
                ttk.Frame(home_page, height=20).pack()
    except Exception:
        pass

    ttk.Label(
        home_page,
        text="PowDroid: A lightweight tool for measuring the energy footprint of any Android application",
        font=("Segoe UI", 10),
        padding=10,
        anchor="w",
        justify="left",
        background=app.style.colors.secondary,
        foreground="white"
    ).pack(pady=(0, 20))
    add_footer(home_page)
    pages["home"] = home_page

    # --- DATA SESSION PAGE ---
    data_session_page = ttk.Frame(app, style="TFrame")

    ttk.Label(
        data_session_page,
        text="Data Session Page",
        font=("Segoe UI", 12, "bold"),
        padding=10
    ).pack(pady=20)

    def refresh_data_session():
        step2_frame.pack_forget()
        step3_frame.pack_forget()
        step4_frame.pack_forget()
        detect_label.config(text="Click 'Detect device' to start.", foreground="white")
        record_label.config(text="")
        process_label.config(text="")
        output_label.config(text="")
        start_record_btn.config(state="normal")
        finish_record_btn.config(state="disabled")
        process_data_btn.config(state="normal")
        generate_btn.config(state="normal")
        session.clear()
        session.update({"start": None, "stop": None, "device": None, "file_name": None, "csv_path": None})

        detect_btn.config(state="normal")

    refresh_btn = ttk.Button(
        data_session_page,
        text="Refresh",
        takefocus=0,
        command=refresh_data_session
    )
    refresh_btn.pack(pady=5)

    session = {"start": None, "stop": None, "device": None, "file_name": None, "csv_path": None}

    # --- STEP 1: Initialize connection ---
    step1_frame = ttk.LabelFrame(
        data_session_page,
        text="Step 1/4: Initialize device connection",
        padding=15
    )
    step1_frame.pack(fill="x", pady=10, padx=10)

    detect_label = ttk.Label(
        step1_frame,
        text="Click 'Detect device' to start.",
        font=("Segoe UI", 10)
    )
    detect_label.pack(anchor="w", pady=(0, 10))

    def on_detect():
        detect_label.config(foreground="orange", text="Searching for device...")
        app.update_idletasks()
        device = adb.get_connected_device()
        if not device:
            detect_label.config(text="No device detected. Please connect your device via USB.", foreground="red")
            adb.wait_for_device_connection(verbose=True)
            device = adb.get_connected_device()
            if not device:
                detect_label.config(text="Device still not detected. Please try again.", foreground="red")
                return
        session["device"] = device
        detect_label.config(text=f"Device detected: {device}", foreground="green")
        adb.kill_all()
        adb.clear_batterystats(verbose=True)
        step2_frame.pack(fill="x", pady=10, padx=10)
        detect_btn.config(state="disabled")

    detect_btn = ttk.Button(
        step1_frame,
        text="Detect device",
        takefocus=0,
        command=on_detect
    )
    detect_btn.pack(anchor="e")

    # --- STEP 2: Start recording (initially hidden) ---
    step2_frame = ttk.LabelFrame(
        data_session_page,
        text="Step 2/4: Start session recording",
        padding=15
    )

    ttk.Label(
        step2_frame,
        text="Disconnect the device, then click 'Start recording'.",
        font=("Segoe UI", 10),
        anchor="w",
        justify="left"
    ).pack(anchor="w", pady=(0, 10))

    record_label = ttk.Label(
        step2_frame,
        text="",
        font=("Segoe UI", 10)
    )
    record_label.pack(anchor="w", pady=(0, 10))

    def on_start_record():
        record_label.config(text="Waiting for device disconnection...", foreground="orange")
        app.update_idletasks()
        adb.wait_for_device_disconnection(verbose=True)
        session["start"] = datetime.now()
        record_label.config(
            text=f"Recording started at {session['start'].strftime('%Y-%m-%d %H:%M:%S')}. Please perform your test.",
            foreground="green"
        )
        start_record_btn.config(state="disabled")
        finish_record_btn.config(state="normal")

    start_record_btn = ttk.Button(
        step2_frame,
        text="Start recording",
        takefocus=0,
        command=on_start_record
    )
    start_record_btn.pack(anchor="e")

    def on_finish_record():
        session["stop"] = datetime.now()
        record_label.config(
            text=f"Recording finished at {session['stop'].strftime('%Y-%m-%d %H:%M:%S')}",
            foreground="blue"
        )
        finish_record_btn.config(state="disabled")
        step3_frame.pack(fill="x", pady=10, padx=10)

    finish_record_btn = ttk.Button(
        step2_frame,
        text="Finish recording",
        takefocus=0,
        command=on_finish_record,
        state="disabled"
    )
    finish_record_btn.pack(anchor="e")

    # --- STEP 3: Process battery data (initially hidden) ---
    step3_frame = ttk.LabelFrame(
        data_session_page,
        text="Step 3/4: Process battery data",
        padding=15
    )
    ttk.Label(
        step3_frame,
        text="Reconnect the device, then click 'Process data'.",
        font=("Segoe UI", 10),
        anchor="w",
        justify="left"
    ).pack(anchor="w", pady=(0, 10))

    process_label = ttk.Label(
        step3_frame,
        text="",
        font=("Segoe UI", 10)
    )
    process_label.pack(anchor="w", pady=(0, 10))

    def on_process_data():
        process_label.config(text="Waiting for device connection...", foreground="orange")
        app.update_idletasks()
        adb.wait_for_device_connection(verbose=True)
        process_label.config(text="Processing battery data...", foreground="green")
        adb.dump_batterystats(verbose=True)
        file_name = adb.conversion_batterystats()
        session["file_name"] = file_name
        process_label.config(text=f"Battery data processed: {file_name}", foreground="green")
        step4_frame.pack(fill="x", pady=10, padx=10)
        process_data_btn.config(state="disabled")

    process_data_btn = ttk.Button(
        step3_frame,
        text="Process data",
        takefocus=0,
        command=on_process_data
    )
    process_data_btn.pack(anchor="e")

    # --- STEP 4: Generate output files (initially hidden) ---
    step4_frame = ttk.LabelFrame(
        data_session_page,
        text="Step 4/4: Generate output files",
        padding=15
    )
    ttk.Label(
        step4_frame,
        text="Select output formats and click 'Generate files' to get the results.",
        font=("Segoe UI", 10),
        anchor="w",
        justify="left"
    ).pack(anchor="w", pady=(0, 10))

    output_csv_var = BooleanVar(value=True)
    output_html_var = BooleanVar(value=True)
    output_graphic_var = BooleanVar(value=False)

    check_csv = ttk.Checkbutton(
        step4_frame, text="CSV", variable=output_csv_var
    )
    check_html = ttk.Checkbutton(
        step4_frame, text="HTML", variable=output_html_var
    )
    check_graphic = ttk.Checkbutton(
        step4_frame, text="Built-in graphic (coming soon)", variable=output_graphic_var, state="disabled"
    )
    check_csv.pack(anchor="w")
    check_html.pack(anchor="w")
    check_graphic.pack(anchor="w")

    output_label = ttk.Label(
        step4_frame,
        text="",
        font=("Segoe UI", 10)
    )
    output_label.pack(anchor="w", pady=(0, 10))

    def on_generate():
        output_label.config(text="Generating output files...", foreground="orange")
        app.update_idletasks()
        if not session.get("file_name") or not session.get("start") or not session.get("stop"):
            output_label.config(text="Missing session data. Please complete previous steps.", foreground="red")
            return

        # Respecte la logique CLI : on génère toujours le CSV si CSV ou HTML est coché
        output_formats = []
        if output_csv_var.get():
            output_formats.append("csv")
        if output_html_var.get():
            output_formats.append("html")

        if not output_formats:
            output_label.config(text="Please select at least one output format.", foreground="red")
            return

        def to_timestamp_ms(dt):
            return int(dt.timestamp() * 1000) if isinstance(dt, datetime) else dt

        start_ts = to_timestamp_ms(session["start"])
        stop_ts = to_timestamp_ms(session["stop"])

        generated = []
        csv_path = None

        # Génération CSV (toujours si CSV ou HTML demandé, comme dans la CLI)
        csv.generate_files(session["file_name"])
        csv_path = csv.process_csv_file(start_ts, stop_ts)
        session["csv_path"] = csv_path

        if "csv" in output_formats and csv_path:
            generated.append(f"CSV: {csv_path}")

        if "html" in output_formats and csv_path:
            html_content = html.process_html_file(csv_path)
            html_path = csv_path.rsplit(".", 1)[0] + ".html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            generated.append(f"HTML: {html_path}")

        if not generated:
            output_label.config(text="Please select at least one output format.", foreground="red")
        else:
            output_label.config(
                text="Files generated:\n" + "\n".join(generated),
                foreground="green"
            )
            generate_btn.config(state="disabled")

    generate_btn = ttk.Button(
        step4_frame,
        text="Generate files",
        takefocus=0,
        command=on_generate
    )
    generate_btn.pack(anchor="e")

    add_footer(data_session_page)
    pages["data_session"] = data_session_page

    # --- UPLOAD DATA PAGE ---
    upload_data_page = ttk.Frame(app, style="TFrame")

    content_frame = ttk.Frame(upload_data_page, style="TFrame")
    content_frame.pack(fill="both", expand=True)

    ttk.Label(
        content_frame,
        text="Upload Data Page",
        font=("Segoe UI", 12, "bold"),
        padding=10
    ).pack(pady=20)

    ttk.Label(
        content_frame,
        text="This section allows you to upload CSV files for built-in view experience.",
        font=("Segoe UI", 10),
        padding=10,
        anchor="w",
        justify="left",
        background=app.style.colors.secondary,
        foreground="white"
    ).pack(pady=(0, 20))

    def upload_csv():
        file_path = filedialog.askopenfilename(
            filetypes=[("CSV files", "*.csv")],
            title="Select a CSV file"
        )
        if not file_path:
            return

        try:
            with open(file_path, newline='', encoding='utf-8') as csvfile:
                reader = pycsv.reader(csvfile)
                rows = list(reader)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read CSV file:\n{e}")
            return

        for widget in content_frame.pack_slaves():
            if isinstance(widget, ttk.Treeview) or isinstance(widget, ttk.Scrollbar):
                widget.destroy()

        if rows:
            columns = rows[0]
            table_frame = ttk.Frame(content_frame)
            table_frame.pack(pady=10, fill="both", expand=True)

            tree = ttk.Treeview(
                table_frame,
                columns=columns,
                show="headings",
                height=10
            )
            for col in columns:
                tree.heading(col, text=col)
                tree.column(col, width=100, anchor="center")
            for row in rows[1:]:
                tree.insert("", "end", values=row)

            vsb = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
            hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
            tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

            tree.grid(row=0, column=0, sticky="nsew")
            vsb.grid(row=0, column=1, sticky="ns")
            hsb.grid(row=1, column=0, sticky="ew")

            table_frame.grid_rowconfigure(0, weight=1)
            table_frame.grid_columnconfigure(0, weight=1)

    upload_btn = ttk.Button(
        content_frame,
        text="Upload CSV",
        takefocus=0,
        command=upload_csv
    )
    upload_btn.pack(pady=10)

    def refresh_table():
        for widget in content_frame.pack_slaves():
            if isinstance(widget, ttk.Frame):
                widget.destroy()

    refresh_btn = ttk.Button(
        content_frame,
        text="Refresh",
        takefocus=0,
        command=refresh_table
    )
    refresh_btn.pack(pady=5)
    add_footer(upload_data_page)
    pages["upload_data"] = upload_data_page

    # --- ABOUT US PAGE ---
    about_us_page = ttk.Frame(app, style="TFrame")

    ttk.Label(
        about_us_page,
        text="About PowDroid",
        font=("Segoe UI", 14, "bold"),
        padding=10
    ).pack(pady=20)

    ttk.Label(
        about_us_page,
        text=(
            "As mentioned on the home page, PowDroid is a lightweight tool designed to measure the energy footprint of any Android application.\n\n"
            "This project was initiated by a team of researchers from the Université de Pau et des Pays de l'Adour (UPPA), who are passionate about energy efficiency and the Android ecosystem.\n\n"
            "If you have any questions or need support, please contact the focal point of this project at olivier.legoaer@univ-pau.fr.\n\n"
            "Version: 1.0.0"
        ),
        font=("Segoe UI", 10),
        anchor="w",
        justify="left",
        wraplength=500
    ).pack(pady=(0, 20), padx=10, anchor="w")
    add_footer(about_us_page)
    pages["about_us"] = about_us_page

    return pages

def show_page(pages, page_name):
    for name, frame in pages.items():
        frame.pack_forget()
    pages[page_name].pack(side="left", fill="both", expand=True, padx=20, pady=20)
