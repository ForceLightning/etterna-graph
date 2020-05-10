from __future__ import annotations
from typing import *

import json, os, glob
from dataclasses import dataclass
from copy import copy

import pyqtgraph as pg
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *

import plotter
import util
import app


"""
This file mainly handles the UI and overall program state
"""

VERSION_NUMBER = "v0.4"

ABOUT_TEXT = """
This was coded using PyQt5 and PyQtGraph in Python, by kangalioo.

The manipulation percentage is calculated by counting the number of
notes that were hit out of order. This is not optimal, but I think it
works well enough.

For session time calculation a session is defined to end when one play
is more than 20 minutes apart from the next play. Therefore a 15min
pause between playing would still count as one session, a 25 min pause
however would not.

Also, if you have any more plot ideas - scatter plot, bar chart,
whatever - I would be thrilled if you sent them to me, over
Discord/Reddit (kangalioo#9108 and u/kangalioo respectively)
""".strip() # strip() to remove leading and trailing newlines

REPLAYS_CHOOSER_INFO_MSG = """
In the following dialog you need to select the ReplaysV2 directory in
your 'Save' directory and click OK. Important: don't try to select
individual files within and don't choose another directory. This
program requires you to select the ReplaysV2 folder as a whole.
""".strip()

NEW_VERSION_MSG = f"""
Version {{0}} is available on the GitHub releases page.
This is version {VERSION_NUMBER}
""".strip()

XML_CANCEL_MSG = "You need to provide an Etterna.xml file for this program to work"
SETTINGS_PATH = "etterna-graph-settings.json"

_keep_storage: List[Any] = []
def keep(*args) -> None:
	_keep_storage.extend(args)

def try_select_xml() -> Optional[str]:
	result = QFileDialog.getOpenFileName(
			caption="Select your Etterna.xml",
			filter="Etterna XML files(Etterna.xml)")
	return result[0] if result else None

def try_choose_replays() -> Optional[str]:
	result = QFileDialog.getExistingDirectory(
			caption="Select the ReplaysV2 directory")
	return result[0] if result else None

@dataclass
class Settings:
	xml_path: str
	replays_dir: str
	enable_all_plots: bool
	
	@staticmethod
	def load_from_json(path: str) -> Settings:
		if os.path.exists(path):
			with open(path) as f:
				j = json.load(f)
			
			return Settings(j["etterna-xml"], j["replays-dir"], j["enable-all-plots"])
		else:
			return Settings(None, None, False)
	
	def save_to_json(self, path: str) -> None:
		json_data = {
			"etterna-xml": self.xml_path,
			"replays-dir": self.replays_dir,
			"enable-all-plots": self.enable_all_plots,
		}
		with open(path, "w") as f:
			json.dump(json_data, f)

class SettingsDialog(QDialog):
	def __init__(self):
		super().__init__()
		self.setWindowTitle("Settings")
		
		vbox = QVBoxLayout(self)
		
		layout_widget = QWidget(self)
		vbox.addWidget(layout_widget)
		layout = QGridLayout(layout_widget)
		
		buttons = QDialogButtonBox()
		save_btn = buttons.addButton("Save", QDialogButtonBox.ButtonRole.AcceptRole)
		save_btn.pressed.connect(self.try_save)
		cancel_btn = buttons.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
		cancel_btn.pressed.connect(self.reject)
		vbox.addWidget(buttons)
		
		restart_info = QLabel("<i>Restart for changes to take place</i>")
		restart_info.setAlignment(Qt.AlignCenter | Qt.AlignRight)
		vbox.addWidget(restart_info)
		
		self.xml_input = QLineEdit(app.app.prefs.xml_path)
		def xml_chooser_handler():
			result = try_select_xml()
			if result: self.xml_input.setText(result)
		layout.addWidget(QLabel("Etterna XML path"), 0, 0)
		layout.addWidget(self.xml_input, 0, 1)
		btn = QPushButton()
		btn.setIcon(QIcon.fromTheme("document-open", QApplication.style().standardIcon(QStyle.SP_DirIcon)))
		btn.pressed.connect(xml_chooser_handler)
		layout.addWidget(btn, 0, 2)
		
		self.replays_input = QLineEdit(app.app.prefs.replays_dir)
		def replays_chooser_handler():
			result = try_choose_replays()
			if result: self.replays_input.setText(result)
		layout.addWidget(QLabel("ReplaysV2 directory path"), 1, 0)
		layout.addWidget(self.replays_input, 1, 1)
		btn = QPushButton()
		btn.setIcon(QIcon.fromTheme("folder-open", QApplication.style().standardIcon(QStyle.SP_DirIcon)))
		btn.pressed.connect(replays_chooser_handler)
		layout.addWidget(btn, 1, 2)
		
		self.enable_all = QCheckBox()
		self.enable_all.setChecked(app.app.prefs.enable_all_plots)
		layout.addWidget(QLabel("Enable experimental plots\n(not recommended)"), 2, 0)
		layout.addWidget(self.enable_all, 2, 1, 1, 2)
		
		self.setMinimumWidth(600)
	
	def try_save(self):
		missing_inputs = []
		if not os.path.exists(self.xml_input.text()): # includes blank input
			missing_inputs.append("Etterna.xml path")
		if not os.path.exists(self.replays_input.text()): # includes blank input
			missing_inputs.append("ReplaysV2 directory")
		if len(missing_inputs) >= 1:
			QMessageBox.information(None, "Missing or invalid fields",
					"Please fill in valid values for: " + ", ".join(missing_inputs))
			return
		
		app.app.prefs.xml_path = self.xml_input.text()
		app.app.prefs.replays_dir = self.replays_input.text()
		app.app.prefs.enable_all_plots = self.enable_all.isChecked()
		print("Saving prefs to json...")
		app.app.prefs.save_to_json(SETTINGS_PATH)
		
		self.accept()

class UI:
	def __init__(self):
		# Construct app, root widget and layout
		self.qapp = QApplication(["Kangalioo's Etterna stats analyzer"])
		
		# Prepare area for the widgets
		window = QMainWindow()
		root = QWidget()
		layout = QVBoxLayout(root)
		
		# setup style
		root.setStyleSheet(f"""
			background-color: {util.bg_color};
			color: {util.text_color};
		""")
		pg.setConfigOption("background", util.bg_color)
		pg.setConfigOption("foreground", util.text_color)
		
		help_menu = window.menuBar().addMenu("Help")
		help_menu.addAction("Settings").triggered.connect(lambda: SettingsDialog().exec_())
		help_menu.addAction("About").triggered.connect(lambda: QMessageBox.about(None, "About", ABOUT_TEXT))

		# Put the widgets in
		self.setup_widgets(layout, window)
		
		# QScrollArea wrapper with scroll wheel scrolling disabled on plots. I did this to prevent
		# simultaneous scrolling and panning when hovering a plot while scrolling
		class ScrollArea(QScrollArea):
			def eventFilter(self, obj, event) -> bool:
				if event.type() == QEvent.Wheel and self.ui_object.plot_container.underMouse():
					return True
				return False
		scroll = ScrollArea(window)
		scroll.ui_object = self
		scroll.setWidget(root)
		scroll.setWidgetResizable(True)
		window.setCentralWidget(scroll)
		
		# Start
		w, h = 1600, 3100
		if app.app.prefs.enable_all_plots: h += 1300 # More plots -> more room
		# ~ root.setMinimumSize(1000, h)
		root.setMinimumHeight(h)
		window.resize(w, h)
		window.show()
		keep(window)
	
	def run(self):
		self.qapp.exec_()
	
	def setup_widgets(self, layout, window):
		# Add infobox
		toolbar = QToolBar()
		infobar = QLabel("This is the infobox. Press on a scatter point to see information about the score")
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
	def run(self):
		self._prefs = Settings.load_from_json(SETTINGS_PATH)
		self._ui = UI()
		self._infobar_link_connection = None
		
		if self._prefs.xml_path is None or self._prefs.replays_dir is None:
			self.try_detect_etterna()
		
		if self._prefs.xml_path is None or self._prefs.replays_dir is None:
			if not self.make_user_choose_paths():
				return
		
		self._prefs.save_to_json(SETTINGS_PATH)
		
		box_container, plot_container = self._ui.get_box_container_and_plot_container()
		plotter.draw(self._ui.get_qapp(), box_container, plot_container, self._prefs)
		
		self._ui.run()
	
	def set_infobar(self, text: str, link_callback=None) -> None:
		if self._infobar_link_connection:
			try:
				self._ui.infobar.disconnect(self._infobar_link_connection)
				self._infobar_link_connection = None
			except TypeError as e:
				util.logger.warning(e)
		self._ui.infobar.setText(text)
		if link_callback:
			self._infobar_link_connection = self._ui.infobar.linkActivated.connect(link_callback)
	
	def make_user_choose_paths(self) -> bool: # return False if user cancelled
		xml_path = try_select_xml()
		if not xml_path:
			text = "You need to provide your Etterna.xml!"
			QMessageBox.critical(None, text, text)
			return False
		self._prefs.xml_path = xml_path
		replays_dir = os.path.abspath(os.path.join(os.path.dirname(xml_path), "../../ReplaysV2"))
		if os.path.exists(replays_dir):
			self._prefs.replays_dir = replays_dir
		else:
			QMessageBox.information(None, "ReplaysV2 could not be found",
					"The ReplaysV2 directory could not be found. Please select it manually in the following dialog")
			SettingsDialog().exec_()
		return True
	
	# Detects an Etterna installation and sets xml_path and
	# replays_dir to the paths in it
	def try_detect_etterna(self):
		globs = [
			"C:\\Games\\Etterna*", # Windows
			"C:\\Users\\*\\AppData\\*\\etterna*", # Windows
			os.path.expanduser("~") + "/.etterna*", # Linux
			os.path.expanduser("~") + "/.stepmania*", # Linux
			"/opt/etterna*", # Linux
			"Y:\\.etterna*", # My Wine on Linux (for testing)
			os.path.expanduser("~") + "/Library/Preferences/Etterna*", # Mac
		]
		# Assemble all possible save game locations. path_pairs is a
		# list of tuples `(xml_path, replays_dir_path)`
		path_pairs = []
		for glob_str in globs:
			for path in glob.iglob(glob_str):
				replays_dir = path + "/Save/ReplaysV2"
				possible_xml_paths = glob.iglob(path + "/Save/LocalProfiles/*/Etterna.xml")
				for xml_path in possible_xml_paths:
					path_pairs.append((xml_path, replays_dir))
		
		if len(path_pairs) == 0:
			return # No installation could be found
		elif len(path_pairs) == 1:
			# Only one was found, but maybe this is the wrong one and
			# the correct xml was not detected at all. Better ask
			mibs = os.path.getsize(path_pairs[0][0]) / 1024**2 # MiB's
			text = f"Detected an Etterna.xml ({mibs:.2f} MiB) at {path_pairs[0][0]}. Should the program use that?"
			reply = QMessageBox.question(None, "Which Etterna.xml?", text,
					QMessageBox.Yes, QMessageBox.No)
			if reply == QMessageBox.No: return
			path_pair = path_pairs[0]
		else: # With multiple possible installations, it's tricky
			# Select the savegame pair with the largest XML, ask user if that one is right
			path_pair = max(path_pairs, key=lambda pair: os.path.getsize(pair[0]))
			mibs = os.path.getsize(path_pair[0]) / 1024**2 # MiB's
			text = f"Found {len(path_pairs)} Etterna.xml's. The largest one \n({path_pair[0]})\nis {mibs:.2f} MiB; should the program use that?"
			reply = QMessageBox.question(None, "Which Etterna.xml?", text,
					QMessageBox.Yes, QMessageBox.No)
			if reply == QMessageBox.No: return
		
		# Apply the paths. Also, do a check if files exist. I mean, they
		# _should_ exist at this point, but you can never be too sure
		xml_path, replays_dir = path_pair
		if os.path.exists(xml_path):
			self._prefs.xml_path = xml_path
		if os.path.exists(replays_dir):
			self._prefs.replays_dir = replays_dir
	
	@property
	def prefs(self):
		return self._prefs

if __name__ == "__main__":
	try:
		app.app = Application()
		app.app.run()
	except Exception:
		# Maybe send an automated e-mail to me on Exception in the future?
		util.logger.exception("Main")
		input("Press enter to quit")