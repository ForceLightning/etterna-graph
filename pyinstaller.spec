# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ["etterna_analysis\\main.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=["dateutil", "pyqtgraph"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "tk", "tcl", "mpl-data", "PySide2"],
    noarchive=False,
    optimize=0,
)


def extra_datas(mydir: str):
    def rec_glob(p: str, files: list[str]):
        import os
        import glob

        for d in glob.glob(p):
            if os.path.isfile(d):
                files.append(d)
            rec_glob("%s/*" % d, files)

    files: list[str] = []
    rec_glob("%s/*" % mydir, files)
    extra_datas: list[tuple[str, str, str]] = []
    for f in files:
        extra_datas.append((f, f, "DATA"))

    return extra_datas


a.datas += extra_datas("etterna_analysis")

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="main",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="main",
)
