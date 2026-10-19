#!/usr/bin/env python3
"""
RTW Campaign HUD Visual Assembler
Dynamic output folders, text tabs, removed stats/help buttons, fixed minimap positioning.
"""

import os
import shutil
import logging
from datetime import datetime
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFileDialog, QComboBox, QMessageBox,
    QGraphicsScene, QGraphicsView, QGraphicsRectItem, QFormLayout,
    QGroupBox, QSpinBox, QSplitter, QSizePolicy, QGraphicsTextItem
)
from PyQt5.QtGui import QColor, QBrush, QPen, QFont, QPixmap, QImage, QPainter
from PyQt5.QtCore import Qt, QRectF, QTimer
from PIL import Image

from sd_xml_parser import SDXMLReader

# Setup Output Directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
NOW_STR = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, f"output_{NOW_STR}")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Setup Logging
LOG_FILE = os.path.join(OUTPUT_DIR, "editor_log.txt")
logging.basicConfig(filename=LOG_FILE, level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s', filemode='w')
logging.info(f"Starting RTW Campaign HUD Editor. Outputs will be saved to: {OUTPUT_DIR}")

# ==============================================================================
# EXACT PIXEL LAYOUT OF THE CAMPAIGN HUD (Based on 1024x768 resolution)
# ==============================================================================
HUD_LAYOUT = {
    "STRAT_HUD_LEFT": (0, 587),
    "STRAT_HUD_MIDDLE": (281, 621),
    "STRAT_HUD_RIGHT": (743, 587),
    
    # Minimap + / - buttons placed at bottom left
    "RADAR_BUTTON_PLUS": (15, 710),
    "RADAR_BUTTON_MINUS": (15, 735),
    
    "BUILD_BUTTON_IMAGE": (760, 620),
    "TRAIN_BUTTON_IMAGE": (760, 695),
    "BUTTON_OUTER_RING_LRG": (880, 650),
    "FACTION_LOGO_ALEMANNI": (897, 667),
    "END_TURN_BUTTON_IMAGE": (970, 680),
    "RADAR_DOT": (130, 680), 
}

DRAW_ORDER = [
    "BUTTON_OUTER_RING_LRG", "FACTION_LOGO_ALEMANNI", 
    "RADAR_BUTTON_PLUS", "RADAR_BUTTON_MINUS",
    "BUILD_BUTTON_IMAGE", "TRAIN_BUTTON_IMAGE",
    "END_TURN_BUTTON_IMAGE", "RADAR_DOT"
]

class HUDEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.game_root = ""
        self.xml_readers = {} 
        self.selected_sprite = None
        self.sprite_rects = []

        self.setWindowTitle("RTW Campaign HUD Editor (Visual)")
        self.resize(1400, 900)
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # --- TOP BAR ---
        top_bar_widget = QWidget()
        top_bar_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        top_bar = QHBoxLayout(top_bar_widget)
        top_bar.setContentsMargins(0, 0, 0, 0)
        
        self.folder_entry = QLineEdit()
        self.folder_entry.setReadOnly(True)
        self.folder_entry.setPlaceholderText("Select RTW game folder...")
        top_bar.addWidget(self.folder_entry)

        btn_browse = QPushButton("Browse Game Folder")
        btn_browse.clicked.connect(self.select_game_folder)
        top_bar.addWidget(btn_browse)

        self.culture_combo = QComboBox()
        self.culture_combo.addItems(["Roman", "Greek", "Eastern", "Barbarian", "Carthaginian", "Egyptian"])
        self.culture_combo.currentTextChanged.connect(self.load_all_campaign_xmls)
        top_bar.addWidget(QLabel("Culture:"))
        top_bar.addWidget(self.culture_combo)

        self.status_label = QLabel("Please select your RTW folder.")
        self.status_label.setStyleSheet("color: orange; font-weight: bold;")
        top_bar.addWidget(self.status_label)

        # Date/Time Label
        self.time_label = QLabel()
        self.time_label.setStyleSheet("color: #333; font-weight: bold; padding-left: 10px;")
        top_bar.addWidget(self.time_label)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)
        self.update_time()

        main_layout.addWidget(top_bar_widget)

        # --- MAIN SPLITTER ---
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Canvas
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setBackgroundBrush(QBrush(QColor("#1e1e1e")))
        self.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.view.setSceneRect(0, 0, 1024, 768)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        splitter.addWidget(self.view)

        # Right Panel
        right_panel = QWidget()
        right_panel.setMinimumWidth(350)
        right_panel.setMaximumWidth(450)
        right_layout = QVBoxLayout(right_panel)

        self.asset_info = QLabel("No element selected.")
        self.asset_info.setStyleSheet("color: gray; font-style: italic;")
        right_layout.addWidget(self.asset_info)

        self.props_group = QGroupBox("Element Crop Properties")
        self.props_group.setEnabled(False)
        form_layout = QFormLayout()

        self.name_label = QLabel("-")
        self.source_label = QLabel("-")
        self.x_spin = QSpinBox()
        self.y_spin = QSpinBox()
        self.w_spin = QSpinBox()
        self.h_spin = QSpinBox()

        for spin in [self.x_spin, self.y_spin, self.w_spin, self.h_spin]:
            spin.setRange(-9999, 9999)
            spin.valueChanged.connect(self.update_sprite)

        form_layout.addRow("Name:", self.name_label)
        form_layout.addRow("Source XML:", self.source_label)
        form_layout.addRow("Crop X:", self.x_spin)
        form_layout.addRow("Crop Y:", self.y_spin)
        form_layout.addRow("Width:", self.w_spin)
        form_layout.addRow("Height:", self.h_spin)

        self.props_group.setLayout(form_layout)
        right_layout.addWidget(self.props_group)

        # Output Folder Info
        folder_info = QLabel(f"Saving outputs to:\n{os.path.basename(OUTPUT_DIR)}")
        folder_info.setStyleSheet("color: #555; font-size: 10px; font-style: italic;")
        right_layout.addWidget(folder_info)

        # Buttons
        btn_export = QPushButton("📷 Export HUD as PNG (1024x768)")
        btn_export.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 5px;")
        btn_export.clicked.connect(self.export_hud_image)
        right_layout.addWidget(btn_export)

        btn_screenshot = QPushButton("📸 Screenshot Program UI")
        btn_screenshot.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 5px;")
        btn_screenshot.clicked.connect(self.take_program_screenshot)
        right_layout.addWidget(btn_screenshot)

        btn_save = QPushButton("Save Changes to XML Files")
        btn_save.clicked.connect(self.save_all_xmls)
        right_layout.addWidget(btn_save)

        right_layout.addStretch()
        splitter.addWidget(right_panel)
        splitter.setSizes([1050, 350])
        main_layout.addWidget(splitter)

    def update_time(self):
        self.time_label.setText(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # ------------------------------------------------------------------
    # Loading Logic
    # ------------------------------------------------------------------
    def select_game_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Game Root Folder")
        if folder and os.path.isdir(os.path.join(folder, "data")):
            self.game_root = folder
            self.folder_entry.setText(folder)
            logging.info(f"Game root folder selected: {folder}")
            self.load_all_campaign_xmls()

    def load_all_campaign_xmls(self):
        if not self.game_root:
            return
            
        self.xml_readers.clear()
        culture = self.culture_combo.currentText().lower()
        logging.info(f"Loading campaign XMLs for culture: {culture}")
        
        required_xmls = ["strat3.sd.xml", "shared2.sd.xml", "radar.sd.xml"]
        loaded_count = 0
        
        for xml_name in required_xmls:
            paths = [
                os.path.join(self.game_root, "data", "ui", culture, "interface", xml_name),
                os.path.join(self.game_root, "data", "ui", culture, xml_name),
                os.path.join(self.game_root, "data", "ui", "roman", "interface", xml_name),
                os.path.join(self.game_root, "data", "ui", "roman", xml_name),
                os.path.join(self.game_root, "data", "ui", xml_name)
            ]
            for p in paths:
                if os.path.exists(p):
                    try:
                        self.xml_readers[xml_name] = SDXMLReader(p)
                        logging.info(f"Loaded XML: {p}")
                        loaded_count += 1
                    except Exception as e:
                        logging.error(f"Error loading {p}: {e}")
                    break
                    
        if loaded_count > 0:
            self.status_label.setText(f"Loaded {loaded_count} HUD files successfully.")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
            self.render_hud()
        else:
            self.status_label.setText("Error: Could not find campaign HUD XMLs.")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")

    def get_image_path(self, filename):
        if "radar_map" in filename.lower():
            primary_dir = os.path.join(self.game_root, "data", "world", "maps", "campaign", "imperial_campaign")
            if os.path.isdir(primary_dir):
                for candidate in ["radar_map2.tga", "radar_map1.tga"]:
                    for f in os.listdir(primary_dir):
                        if f.lower() == candidate:
                            return os.path.join(primary_dir, f)

        culture = self.culture_combo.currentText().lower()
        search_dirs = [
            os.path.join(self.game_root, "data", "ui", culture, "interface"),
            os.path.join(self.game_root, "data", "ui", culture),
            os.path.join(self.game_root, "data", "ui", "roman", "interface"),
            os.path.join(self.game_root, "data", "ui", "roman"),
            os.path.join(self.game_root, "data", "ui")
        ]
        
        for d in search_dirs:
            if os.path.isdir(d):
                for f in os.listdir(d):
                    if f.lower() == filename.lower():
                        return os.path.join(d, f)
        return None

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def render_hud(self):
        self.scene.clear()
        self.sprite_rects.clear()
        self.props_group.setEnabled(False)

        # 1. Dark Green Background
        self.scene.addRect(0, 0, 1024, 768, QPen(Qt.NoPen), QBrush(QColor("#2b3b22")))
        
        sprites_to_draw = []
        for xml_name, reader in self.xml_readers.items():
            for sprite in reader.sprites:
                if sprite.name in HUD_LAYOUT:
                    sprites_to_draw.append((sprite, reader))

        # 2. Marble Panels
        backgrounds = ["STRAT_HUD_LEFT", "STRAT_HUD_MIDDLE", "STRAT_HUD_RIGHT"]
        for sprite, reader in sprites_to_draw:
            if sprite.name in backgrounds:
                draw_x, draw_y = HUD_LAYOUT[sprite.name]
                tga_path = self.get_image_path(reader.pages[sprite.page_index].file_name)
                if tga_path:
                    try:
                        img = Image.open(tga_path).convert("RGBA")
                        crop = img.crop((sprite.x, sprite.y, sprite.x + sprite.w, sprite.y + sprite.h))
                        data = crop.tobytes("raw", "RGBA")
                        qim = QImage(data, crop.width, crop.height, QImage.Format_RGBA8888)
                        pix_item = self.scene.addPixmap(QPixmap.fromImage(qim))
                        pix_item.setPos(draw_x, draw_y)
                    except Exception: pass
                
                rect = QGraphicsRectItem(draw_x, draw_y, sprite.w, sprite.h)
                rect.setPen(QPen(Qt.NoPen))
                rect.setFlag(QGraphicsRectItem.ItemIsSelectable, True)
                rect.sprite_data = sprite
                rect.reader_ref = reader 
                self.scene.addItem(rect)
                self.sprite_rects.append(rect)

        # 3. Minimap (Positioned 30, 605, size 210x150)
        map_path = self.get_image_path("radar_map2.tga")
        if map_path:
            try:
                img = Image.open(map_path).convert("RGBA")
                img = img.resize((210, 150), Image.Resampling.LANCZOS)
                data = img.tobytes("raw", "RGBA")
                qim = QImage(data, img.width, img.height, QImage.Format_RGBA8888)
                pix_item = self.scene.addPixmap(QPixmap.fromImage(qim))
                pix_item.setPos(30, 605) 
            except Exception as e: logging.error(f"Map render error: {e}")

        # 4. Draw Text Tabs
        tab_font = QFont("Times New Roman", 12, QFont.Bold)
        # Draw the tabs starting at x=284, width ~70 each
        for text, x_pos in [("Army", 294), ("Town", 364), ("Agents", 434)]:
            text_item = self.scene.addText(text, tab_font)
            text_item.setDefaultTextColor(QColor("#332211")) # Dark brown for visibility on marble
            # Center the text roughly
            text_item.setPos(x_pos, 592)

        # 5. Other Elements (Buttons, Radar Dot)
        others = [s for s in sprites_to_draw if s[0].name not in backgrounds]
        others.sort(key=lambda item: DRAW_ORDER.index(item[0].name) if item[0].name in DRAW_ORDER else 999)

        for sprite, reader in others:
            draw_x, draw_y = HUD_LAYOUT[sprite.name]
            tga_path = self.get_image_path(reader.pages[sprite.page_index].file_name)
            
            if tga_path:
                try:
                    img = Image.open(tga_path).convert("RGBA")
                    crop = img.crop((sprite.x, sprite.y, sprite.x + sprite.w, sprite.y + sprite.h))
                    data = crop.tobytes("raw", "RGBA")
                    qim = QImage(data, crop.width, crop.height, QImage.Format_RGBA8888)
                    pix_item = self.scene.addPixmap(QPixmap.fromImage(qim))
                    pix_item.setPos(draw_x, draw_y)
                except Exception: pass

            rect = QGraphicsRectItem(draw_x, draw_y, sprite.w, sprite.h)
            rect.setPen(QPen(Qt.NoPen))
            rect.setFlag(QGraphicsRectItem.ItemIsSelectable, True)
            rect.sprite_data = sprite
            rect.reader_ref = reader 
            self.scene.addItem(rect)
            self.sprite_rects.append(rect)

        self.scene.selectionChanged.connect(self.on_selection_changed)
        if self.selected_sprite is None:
            self.view.fitInView(self.view.sceneRect(), Qt.KeepAspectRatio)

    # ------------------------------------------------------------------
    # Selection and editing
    # ------------------------------------------------------------------
    def on_selection_changed(self):
        for r in self.sprite_rects: r.setPen(QPen(Qt.NoPen))

        selected_items = self.scene.selectedItems()
        if not selected_items:
            self.props_group.setEnabled(False)
            self.selected_sprite = None
            self.asset_info.setText("No element selected.")
            self.asset_info.setStyleSheet("color: gray; font-style: italic;")
            return

        # Ensure we are clicking a UI sprite box, not the text items we created
        rect_item = None
        for item in selected_items:
            if isinstance(item, QGraphicsRectItem):
                rect_item = item
                break
                
        if not rect_item or not hasattr(rect_item, 'sprite_data'):
            return

        self.selected_sprite = rect_item.sprite_data
        self.current_reader = rect_item.reader_ref
        self.props_group.setEnabled(True)
        self.name_label.setText(self.selected_sprite.name)
        self.source_label.setText(os.path.basename(self.current_reader.filepath))
        self.asset_info.setText(f"Editing: {self.selected_sprite.name}")
        self.asset_info.setStyleSheet("color: lime; font-weight: bold;")

        rect_item.setPen(QPen(QColor("red"), 2))
        for spin in [self.x_spin, self.y_spin, self.w_spin, self.h_spin]: spin.blockSignals(True)
        self.x_spin.setValue(self.selected_sprite.x)
        self.y_spin.setValue(self.selected_sprite.y)
        self.w_spin.setValue(self.selected_sprite.w)
        self.h_spin.setValue(self.selected_sprite.h)
        for spin in [self.x_spin, self.y_spin, self.w_spin, self.h_spin]: spin.blockSignals(False)

    def update_sprite(self):
        if not self.selected_sprite: return
        self.selected_sprite.x = self.x_spin.value()
        self.selected_sprite.y = self.y_spin.value()
        self.selected_sprite.w = self.w_spin.value()
        self.selected_sprite.h = self.h_spin.value()
        self.render_hud()
        for r in self.sprite_rects:
            if hasattr(r, 'sprite_data') and r.sprite_data == self.selected_sprite:
                r.setPen(QPen(QColor("red"), 2))
                r.setSelected(True)
                break

    # ------------------------------------------------------------------
    # Exporting and Saving
    # ------------------------------------------------------------------
    def export_hud_image(self):
        if not self.xml_readers:
            QMessageBox.warning(self, "Warning", "No HUD loaded to export.")
            return

        for r in self.sprite_rects: r.setPen(QPen(Qt.NoPen))

        rect = QRectF(0, 0, 1024, 768)
        image = QImage(1024, 768, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        
        painter = QPainter(image)
        self.scene.render(painter, rect, rect)
        painter.end()

        default_path = os.path.join(OUTPUT_DIR, "campaign_hud_preview.png")
        file_path, _ = QFileDialog.getSaveFileName(self, "Save HUD Image", default_path, "PNG Image (*.png)")
        
        if file_path:
            image.save(file_path)
            logging.info(f"Exported HUD image to: {file_path}")
            QMessageBox.information(self, "Exported", f"HUD image successfully saved to:\n{file_path}")

        selected_items = self.scene.selectedItems()
        if selected_items: 
            for item in selected_items:
                if isinstance(item, QGraphicsRectItem):
                    item.setPen(QPen(QColor("red"), 2))
                    break

    def take_program_screenshot(self):
        default_name = f"program_screenshot_{datetime.now().strftime('%H%M%S')}.png"
        default_path = os.path.join(OUTPUT_DIR, default_name)
        
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Program Screenshot", default_path, "PNG Image (*.png)")
        
        if file_path:
            pixmap = self.grab()
            pixmap.save(file_path)
            logging.info(f"Saved program screenshot to: {file_path}")
            QMessageBox.information(self, "Saved", f"Program screenshot saved to:\n{file_path}")

    def save_all_xmls(self):
        if not self.xml_readers: return
        saved_files = []
        try:
            for xml_name, reader in self.xml_readers.items():
                backup = reader.filepath + ".bak"
                shutil.copy2(reader.filepath, backup)
                reader.save()
                saved_files.append(xml_name)
                logging.info(f"Saved changes to: {reader.filepath}")
            QMessageBox.information(self, "Saved", f"Successfully saved changes to:\n{', '.join(saved_files)}")
        except Exception as e:
            logging.error(f"Could not save XML files: {e}")
            QMessageBox.critical(self, "Error", f"Could not save file:\n{e}")