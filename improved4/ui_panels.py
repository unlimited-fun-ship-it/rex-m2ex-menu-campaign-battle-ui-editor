#!/usr/bin/env python3
"""Widget construction: top bar (game folder), texture browser, canvas and right-hand controls."""

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox,
    QFormLayout, QGroupBox, QSpinBox, QSplitter, QSlider, QCheckBox, QSizePolicy,
    QTableWidget, QHeaderView, QAbstractItemView,
)

import config


class PanelsMixin:
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main = QVBoxLayout(central)
        main.setContentsMargins(6, 2, 6, 4)
        main.setSpacing(4)

        main.addWidget(self._build_top_bar())  # fixed height: sits right under the menu bar

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_browser_panel())
        splitter.addWidget(self.view)
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([320, 880, 350])
        main.addWidget(splitter, 1)  # stretch 1: the editor area takes all spare space

    # ---------------------------------------------------------------- top bar
    def _build_top_bar(self):
        bar = QWidget()
        bar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)

        self.folder_entry = QLineEdit()
        self.folder_entry.setReadOnly(True)
        self.folder_entry.setPlaceholderText("Select game folder (the one containing 'data')...")
        row.addWidget(self.folder_entry, 1)

        btn = QPushButton("Browse Game Folder")
        btn.clicked.connect(self.select_game_folder)
        row.addWidget(btn)

        row.addWidget(QLabel("Culture:"))
        self.culture_combo = QComboBox()
        self.culture_combo.addItems(config.CULTURES)
        self.culture_combo.currentTextChanged.connect(lambda _: self.load_game_data())
        row.addWidget(self.culture_combo)

        self.status_label = QLabel("Please select your game folder.")
        self.status_label.setStyleSheet("color: orange; font-weight: bold;")
        row.addWidget(self.status_label)
        return bar

    # ------------------------------------------------------- texture browser
    def _build_browser_panel(self):
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel("<b>Texture Browser</b> (double-click to add to the HUD)"))

        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by name...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter_table)
        lay.addWidget(self.search)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["", "Name", "File", "X", "Y", "W", "H"])
        self.table.setIconSize(QSize(48, 48))
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        self.table.itemDoubleClicked.connect(self.add_from_browser)
        lay.addWidget(self.table)
        return panel

    # ------------------------------------------------------------ right panel
    def _build_right_panel(self):
        panel = QWidget()
        panel.setMinimumWidth(330)
        panel.setMaximumWidth(480)
        lay = QVBoxLayout(panel)

        self.chk_builder = QCheckBox("HUD Builder Mode (drag && drop)")
        self.chk_builder.setChecked(True)
        self.chk_builder.setStyleSheet("font-weight: bold; color: #0055aa;")
        self.chk_builder.stateChanged.connect(self.apply_flags)
        lay.addWidget(self.chk_builder)

        self.chk_lock_bg = QCheckBox("Lock HUD background panels")
        self.chk_lock_bg.setChecked(True)
        self.chk_lock_bg.stateChanged.connect(self.apply_flags)
        lay.addWidget(self.chk_lock_bg)

        self.chk_extras = QCheckBox("Show in-game extras (minimap box, arrows, income)")
        self.chk_extras.setChecked(True)
        self.chk_extras.stateChanged.connect(lambda _: self.rebuild())
        lay.addWidget(self.chk_extras)
        self.chk_radar = QCheckBox("Show radar map image in minimap")
        self.chk_radar.stateChanged.connect(lambda _: self.rebuild())
        lay.addWidget(self.chk_radar)

        snap_row = QHBoxLayout()
        snap_row.addWidget(QLabel("Snap to grid (px):"))
        self.snap_spin = QSpinBox()
        self.snap_spin.setRange(1, 64)
        snap_row.addWidget(self.snap_spin)
        lay.addLayout(snap_row)

        lay.addWidget(self._build_props_group())
        lay.addWidget(self._build_background_group())

        for text, slot, style in (
            ("Save Layout  (Ctrl+S)", self.save_layout, ""),
            ("Export HUD as PNG", self.export_png,
             "background-color:#4CAF50;color:white;font-weight:bold;padding:5px;"),
            ("Screenshot Program UI", self.screenshot,
             "background-color:#2196F3;color:white;font-weight:bold;padding:5px;"),
            ("Save Crop Changes to XML Files", self.save_all_xmls, ""),
        ):
            btn = QPushButton(text)
            btn.setStyleSheet(style)
            btn.clicked.connect(slot)
            lay.addWidget(btn)
        lay.addStretch()
        return panel

    def _build_props_group(self):
        self.props = QGroupBox("Selected Element")
        self.props.setEnabled(False)
        form = QFormLayout()
        self.name_label = QLabel("-")
        self.name_label.setWordWrap(True)
        self.source_label = QLabel("-")
        form.addRow("Name:", self.name_label)
        form.addRow("Source XML:", self.source_label)

        self.px, self.py = QSpinBox(), QSpinBox()
        self.cx, self.cy, self.cw, self.ch = QSpinBox(), QSpinBox(), QSpinBox(), QSpinBox()
        for s in (self.px, self.py):
            s.setRange(-2048, 4096)
            s.valueChanged.connect(self.on_pos_spin)
        for s in (self.cx, self.cy, self.cw, self.ch):
            s.setRange(0, 9999)
            s.valueChanged.connect(self.on_crop_spin)
        form.addRow("HUD X:", self.px)
        form.addRow("HUD Y:", self.py)
        form.addRow("Crop X:", self.cx)
        form.addRow("Crop Y:", self.cy)
        form.addRow("Crop W:", self.cw)
        form.addRow("Crop H:", self.ch)

        btn_rm = QPushButton("Remove from HUD")
        btn_rm.setStyleSheet("background-color: #D32F2F; color: white; font-weight: bold;")
        btn_rm.clicked.connect(self.remove_selected)
        form.addRow(btn_rm)
        self.props.setLayout(form)
        return self.props

    def _build_background_group(self):
        group = QGroupBox("Background / Reference")
        form = QFormLayout()
        btn = QPushButton("Load Background Image...")
        btn.clicked.connect(self.load_background)
        form.addRow(btn)

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.valueChanged.connect(self.on_bg_sliders)
        form.addRow("Opacity:", self.opacity_slider)

        self.fade_slider = QSlider(Qt.Horizontal)
        self.fade_slider.setRange(0, 100)
        self.fade_slider.valueChanged.connect(self.on_bg_sliders)
        form.addRow("Fade in from top:", self.fade_slider)

        ref_btn = QPushButton("Load In-Game Screenshot (overlay)...")
        ref_btn.clicked.connect(self.load_reference)
        form.addRow(ref_btn)
        self.chk_ref = QCheckBox("Show screenshot overlay")
        self.chk_ref.stateChanged.connect(self.update_reference)
        form.addRow(self.chk_ref)
        self.ref_slider = QSlider(Qt.Horizontal)
        self.ref_slider.setRange(0, 100)
        self.ref_slider.setValue(50)
        self.ref_slider.valueChanged.connect(self.update_reference)
        form.addRow("Overlay opacity:", self.ref_slider)
        group.setLayout(form)
        return group
