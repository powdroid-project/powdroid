# PyInstaller spec of the PowDroid application (the graphical interface), built by
# .github/workflows/release.yml: pyinstaller packaging/powdroid.spec
# adb is not included (the platform-tools license does not allow redistributing it): PowDroid
# finds the one installed with the Android SDK (see powdroid/core/adb.py).
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
PACKAGE = ROOT / "powdroid"

a = Analysis(
    [str(ROOT / "packaging" / "powdroid_gui.py")],
    pathex=[str(ROOT)],
    datas=[
        (str(PACKAGE / "gui" / "ressources"), "powdroid/gui/ressources"),
        (str(PACKAGE / "gui" / "languages"), "powdroid/gui/languages"),
        (str(PACKAGE / "core" / "vendor"), "powdroid/core/vendor"),
    ],
    # Optional imports of matplotlib and others that PowDroid never uses.
    excludes=["tkinter", "IPython", "jupyter", "notebook", "pandas", "scipy", "sklearn", "torch", "tensorflow",
              "transformers", "tokenizers", "lxml", "PIL.ImageQt", "PyQt5", "PySide2", "PySide6"],
)
pyz = PYZ(a.pure)
icon = str(PACKAGE / "gui" / "ressources" / "powdroid_logo.ico") if sys.platform == "win32" else None
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PowDroid", console=False, icon=icon)
coll = COLLECT(exe, a.binaries, a.datas, name="PowDroid")
if sys.platform == "darwin":
    app = BUNDLE(coll, name="PowDroid.app", bundle_identifier="org.powdroid.PowDroid",
                 info_plist={"NSHighResolutionCapable": True})
