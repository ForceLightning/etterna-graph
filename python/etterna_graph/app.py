from __future__ import annotations
from enum import Enum
import glob
import json
import os
from typing import *

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import pyqtgraph as pg

from etterna_graph import plotter, util
from etterna_graph.settings import (
    Settings,
    SettingsDialog,
    try_choose_replays,
    try_choose_songs_root,
    try_select_xml,
)


"""
This file mainly handles the UI and overall program state
"""

ABOUT_TEXT = """<p>
This was coded using PyQt5 and PyQtGraph in Python, by kangalioo.

The manipulation percentage is calculated by counting the number of
notes that were hit out of order. This is not optimal, but I think it
works well enough.

For session time calculation a session is defined to end when one play
is more than 1 hours apart from the next play.

Also, if you have any more plot ideas - scatter plot, bar chart,
whatever - I would be thrilled if you sent them to me, over
Discord/Reddit (kangalioo#9108 and u/kangalioo respectively)
</p>""".strip()


class UI:
    def __init__(self):
        # Construct app, root widget and layout
        self.qapp = QApplication(["Kangalioo's Etterna stats analyzer"])

        # Prepare area for the widgets
        window = QMainWindow()
        root = QWidget()
        layout = QVBoxLayout(root)

        # setup style
        root.setStyleSheet(
            f"""
			background-color: {util.bg_color()};
			color: {util.text_color()};
		"""
        )
        pg.setConfigOption("background", util.bg_color())
        pg.setConfigOption("foreground", util.text_color())

        main_menu = window.menuBar().addMenu("File")
        main_menu.addAction("Settings").triggered.connect(
            lambda: SettingsDialog().exec_()
        )
        main_menu.addAction("About").triggered.connect(
            lambda: QMessageBox.about(None, "About", ABOUT_TEXT)
        )

        # Put the widgets in
        self.setup_widgets(layout, window)

        # QScrollArea wrapper with scroll wheel scrolling disabled on plots. I did this to prevent
        # simultaneous scrolling and panning when hovering a plot while scrolling
        class ScrollArea(QScrollArea):
            @override
            def eventFilter(self, _obj, event: QEvent) -> bool:
                if event.type() == QEvent.Wheel and any(
                    w.underMouse() for w in app.get_pg_plots()
                ):
                    return True
                return False

        scroll = ScrollArea(window)
        scroll.setWidget(root)
        scroll.setWidgetResizable(True)
        window.setCentralWidget(scroll)

        # Start
        w, h = 1600, 3100
        if app.prefs.enable_all_plots:
            h += 1300  # More plots -> more room
        # ~ root.setMinimumSize(1000, h)
        root.setMinimumHeight(h)
        window.resize(w, h)
        window.show()
        util.keep(window)

    def run(self):
        self.qapp.exec_()

    def setup_widgets(self, layout, window):
        # Add infobox
        toolbar = QToolBar()
        infobar = QLabel(
            "This is the infobox. Press on a scatter point to see information about the score"
        )
        infobar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        infobar.setAlignment(Qt.AlignCenter)
        self.infobar = infobar
        toolbar.addWidget(infobar)
        window.addToolBar(Qt.BottomToolBarArea, toolbar)

        self.box_container = QWidget()
        layout.addWidget(self.box_container)
        self.plot_container = QWidget()
        layout.addWidget(self.plot_container)

    def get_box_container_and_plot_container(self):
        return self.box_container, self.plot_container

    def get_qapp(self):
        return self.qapp


# Handles general application state
class Application:
    def __init__(self) -> None:
        self._pg_plots: list[QWidget] = []
        self._prefs: Settings
        self._ui: UI
        self._infobar_link_connection: QMetaObject.Connection | None = None

    def run(self) -> None:
        self._prefs = Settings.load_from_json()
        self._ui = UI()

        if self._prefs.is_incomplete():
            self.try_detect_etterna()

        if self._prefs.is_incomplete():
            if not self.make_user_choose_paths():
                return

        self._prefs.save_to_json()

        box_container, plot_container = self._ui.get_box_container_and_plot_container()
        self._pg_plots = plotter.draw(
            self._ui.get_qapp(), box_container, plot_container, self._prefs
        )

        self._ui.run()

    def process_events(self):
        self._ui.qapp.processEvents()

    def get_pg_plots(self) -> Optional[List[QWidget]]:
        return self._pg_plots

    def set_infobar(self, text: str, link_callback=None) -> None:
        if self._infobar_link_connection:
            try:
                self._ui.infobar.disconnect(self._infobar_link_connection)
                self._infobar_link_connection = None
            except TypeError as e:
                util.logger.warning(e)
        self._ui.infobar.setText(text)
        if link_callback:
            self._infobar_link_connection = self._ui.infobar.linkActivated.connect(
                link_callback
            )

    def make_user_choose_paths(self) -> bool:  # return False if user cancelled
        xml_path = try_select_xml()
        if not xml_path:
            text = "You need to provide your Etterna.xml!"
            QMessageBox.critical(None, text, text)
            return False
        self._prefs.xml_path = xml_path

        replays_dir = os.path.abspath(
            os.path.join(os.path.dirname(xml_path), "../../ReplaysV2")
        )
        if os.path.exists(replays_dir):
            self._prefs.replays_dir = replays_dir

        songs_root = os.path.abspath(
            os.path.join(os.path.dirname(xml_path), "../../../Songs")
        )
        if os.path.exists(songs_root):
            self._prefs.songs_root = songs_root

        if self._prefs.replays_dir is None or self._prefs.songs_root is None:
            _ = QMessageBox.information(
                None,
                "Couldn't locate game data",
                "The ReplaysV2 directory and/or root songs directory could not be found. "
                + "Please select it manually in the following dialog",
            )
            _ = SettingsDialog().exec_()

        return True

    # Detects an Etterna installation and sets xml_path and
    # replays_dir to the paths in it
    def try_detect_etterna(self):
        globs = [
            "C:\\Games\\Etterna*",  # Windows
            "C:\\Users\\*\\AppData\\*\\etterna*",  # Windows
            os.path.expanduser("~") + "/.etterna*",  # Linux
            os.path.expanduser("~") + "/.stepmania*",  # Linux
            "/opt/etterna*",  # Linux
            "Y:\\.etterna*",  # My Wine on Linux (for testing)
            os.path.expanduser("~") + "/Library/Preferences/Etterna*",  # Mac
        ]
        # Assemble all possible save game locations. path_tuples is a
        # list of tuples `(xml_path, replays_dir_path, songs_root)`
        path_tuples: list[tuple[str, str, str]] = []
        for glob_str in globs:
            for path in glob.iglob(glob_str):
                replays_dir = path + "/Save/ReplaysV2"
                songs_root = path + "/Songs"
                possible_xml_paths = glob.iglob(
                    path + "/Save/LocalProfiles/*/Etterna.xml"
                )
                for xml_path in possible_xml_paths:
                    path_tuples.append((xml_path, replays_dir, songs_root))

        if len(path_tuples) == 0:
            return  # No installation could be found
        elif len(path_tuples) == 1:
            # Only one was found, but maybe this is the wrong one and
            # the correct xml was not detected at all. Better ask
            mibs = os.path.getsize(path_tuples[0][0]) / 1024**2  # MiB's
            text = f"Detected an Etterna.xml ({mibs:.2f} MiB) at {path_tuples[0][0]}. Should the program use that?"
            reply = QMessageBox.question(
                None, "Which Etterna.xml?", text, QMessageBox.Yes, QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
            path_pair = path_tuples[0]
        else:  # With multiple possible installations, it's tricky
            # Select the savegame pair with the largest XML, ask user if that one is right
            path_pair = max(path_tuples, key=lambda pair: os.path.getsize(pair[0]))
            mibs = os.path.getsize(path_pair[0]) / 1024**2  # MiB's
            text = f"Found {len(path_tuples)} Etterna.xml's. The largest one \n({path_pair[0]})\nis {mibs:.2f} MiB; should the program use that?"
            reply = QMessageBox.question(
                None, "Which Etterna.xml?", text, QMessageBox.Yes, QMessageBox.No
            )
            if reply == QMessageBox.No:
                return

        # Apply the paths. Also, do a check if files exist. I mean, they
        # _should_ exist at this point, but you can never be too sure
        xml_path, replays_dir, songs_root = path_pair
        if os.path.exists(xml_path):
            self._prefs.xml_path = xml_path
        if os.path.exists(replays_dir):
            self._prefs.replays_dir = replays_dir
        if os.path.exists(songs_root):
            self._prefs.songs_root = songs_root

    @property
    def prefs(self):
        return self._prefs


# This is the global state (Application object). Accessible from
# everywhere, because it was getting real annoying it not being
# accessible from everywhere.
app: None | Application = None
