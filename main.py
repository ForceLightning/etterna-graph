from PyQt5.QtWidgets import QApplication, QFileDialog, QPushButton, QVBoxLayout, QHBoxLayout, QWidget, QScrollArea, QFrame, QMainWindow, QMessageBox, QSizePolicy
from PyQt5.QtCore import Qt
"""from matplotlib.backends.qt_compat import QtCore, QtWidgets
from matplotlib.backends.backend_qt5agg import FigureCanvas, NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
"""
import numpy as np

import graphing
from plot_frame import PlotFrame

"""
This file mainly handles the UI and overall program state
"""

infobox_text = """
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
Discord/Reddit
""".strip() # strip() to remove leading and trailing newlines

# Fields: etterna_xml, canvas, button_load_xml, button_load_replays, window
class Application():
	#etterna_xml = None
	etterna_xml = "/home/kangalioo/.etterna/Save/LocalProfiles/00000000/Etterna.xml"
	replays_dir = None
	
	def __init__(self):
		# Construct app, root widget and layout 
		app = QApplication(["Kangalioo's Etterna stats analyzer"])
		app.setStyle("Fusion")
		
		window = QMainWindow()
		self.window = window
		root = QWidget()
		layout = QVBoxLayout(root)
		scroll = QScrollArea(window)
		scroll.setWidget(root)
		scroll.setWidgetResizable(True)
		window.setCentralWidget(scroll)
		
		self.setup_ui(layout)
		
		# Start
		root.setMinimumSize(root.sizeHint())
		window.resize(root.sizeHint())
		window.show()
		app.exec_()
	
	def setup_ui(self, layout):
		button_row_widget = QWidget()
		button_row = QHBoxLayout(button_row_widget)
		layout.addWidget(button_row_widget)
		
		button = QPushButton("Reload Etterna.xml")
		self.button_load_xml = button
		button_row.addWidget(button)
		button.clicked.connect(self.try_load_etterna_xml)
		
		button = QPushButton("Load Replays")
		button.setToolTip("Replay data is required for the manipulation chart")
		self.button_load_replays = button
		button_row.addWidget(button)
		button.clicked.connect(self.try_load_replays)
		
		button = QPushButton("About this program")
		button_row.addWidget(button)
		button.clicked.connect(self.display_info_box)
		
		self.plot_frame = PlotFrame(self.etterna_xml)
		layout.addWidget(self.plot_frame)
		
		"""self.canvas = FigureCanvas(Figure(figsize=(12, 16)))
		layout.addWidget(self.canvas)
		
		navigation_toolbar = NavigationToolbar(self.canvas, self.window)
		navigation_toolbar.setMaximumWidth(600)
		button_row.addWidget(navigation_toolbar)"""
		
		# REMEMBER
		#self.try_load_etterna_xml()
		self.refresh_graphs()
	
	def refresh_graphs(self):
		self.plot_frame.draw()
	
	def display_info_box(self):
		msgbox = QMessageBox()
		msgbox.setText(infobox_text)
		msgbox.exec_()
	
	def mark_currently_loaded(self, button):
		current_text = button.text()
		if not current_text.endswith(" [currently loaded]"):
			button.setText(current_text + " [currently loaded]")
	
	def try_load_etterna_xml(self):
		result = QFileDialog.getOpenFileName(filter="Etterna XML files(*.xml)")
		path = result[0] # getOpenFileName returns tuple of path and filetype
		
		if path == "": return # User had cancelled the file chooser
		
		print(f"[UI] User selected Etterna.xml: {path}")
		self.mark_currently_loaded(self.button_load_xml)
		self.etterna_xml = path
		
		self.refresh_graphs()
	
	def try_load_replays(self):
		path = QFileDialog.getExistingDirectory(None, "Select ReplaysV2 folder")
		
		if path == "": return # User had cancelled the chooser
		
		print(f"[UI] User selected ReplaysV2: {path}")
		self.mark_currently_loaded(self.button_load_replays)
		self.replays_dir = path
		
		self.refresh_graphs()

application = Application()
