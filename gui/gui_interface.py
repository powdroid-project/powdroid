from core.utils import page_manager as pm
from core.utils import sidebar_manager as sm

from pathlib import Path
import ttkbootstrap as tb
from ttkbootstrap.constants import *

def main():
    app = tb.Window(themename="darkly")
    app.title("PowDroid GUI")

    ICO_DIR = Path(__file__).resolve().parent / "ressources"
    try:
        app.iconbitmap(ICO_DIR / "powdroid_logo.ico")
    except Exception:
        pass

    app.state("zoomed")

    # --- PAGE SYSTEM SETUP ---
    pages = pm.create_pages(app)

    # --- SIDEBAR ---
    sm.setup_sidebar(app, pages, pm.show_page)

    # --- SHOW HOME PAGE BY DEFAULT ---
    pm.show_page(pages, "home")

    app.mainloop()

if __name__ == "__main__":
    main()
