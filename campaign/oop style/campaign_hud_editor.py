#!/usr/bin/env python3
"""
RTW Campaign HUD Visual Assembler
Main GUI Window.
"""

import os
import shutil
import json
from datetime import datetime

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFileDialog, QComboBox, QMessageBox,
    QGraphicsScene, QGraphicsView, QGraphicsRectItem, QFormLayout,
    QGroupBox, QSpinBox, QSplitter, QSizePolicy, QSlider, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
)
from PyQt5.QtGui import QColor, QBrush, QPen, QFont, QPixmap, QImage, QPainter
from PyQt5.QtCore import Qt, QRectF, QTimer
from PIL import Image, ImageDraw

# Import our custom modules
import config
from sd_xml_parser import SDXMLReader
from canvas_items import DraggableSprite
from asset_manager import AssetManager

class HUDEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.game_root = ""
        self.xml_readers = {} 
        self.selected_sprite = None
        self.sprite_rects = []
        
        self.active_layout = dict(config.DEFAULT_LAYOUT)
        self.all_available_sprites = [] 
        
        # Initialize Asset Manager
        self.assets = AssetManager()
        
        self.bg_image_path = None
        self.bg_opacity = 100
        self.bg_fade = 0

        self.setWindowTitle("RTW Campaign HUD Editor (Visual)")
        self.resize(1600, 950)
        self._build_ui()
        self.load_saved_layout()

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

        self.time_label = QLabel()
        self.time_label.setStyleSheet("color: #333; font-weight: bold; padding-left: 10px;")
        top_bar.addWidget(self.time_label)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)
        self.update_time()

        main_layout.addWidget(top_bar_widget)

        # --- MAIN SPLITTER ---
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)

        # 1. Left Panel: Texture Browser
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        left_layout.addWidget(QLabel("<b>Texture Browser</b> (Double-click to add)"))
        
        self.texture_table = QTableWidget()
        self.texture_table.setColumnCount(5)
        self.texture_table.setHorizontalHeaderLabels(["Preview", "Name", "File", "X", "Y"])
        self.texture_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.texture_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.texture_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.texture_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.texture_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.texture_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.texture_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.texture_table.setSortingEnabled(True)
        self.texture_table.verticalHeader().setVisible(False)
        self.texture_table.itemDoubleClicked.connect(self.add_from_browser)
        left_layout.addWidget(self.texture_table)
        
        self.main_splitter.addWidget(left_panel)

        # 2. Center Panel: Canvas
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setBackgroundBrush(QBrush(QColor("#1e1e1e")))
        self.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.view.setSceneRect(0, 0, 1024, 768)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.main_splitter.addWidget(self.view)

        # 3. Right Panel: Properties & Controls
        right_panel = QWidget()
        right_panel.setMinimumWidth(350)
        right_panel.setMaximumWidth(500)
        right_layout = QVBoxLayout(right_panel)

        self.chk_builder_mode = QCheckBox("HUD Builder Mode (Drag & Drop)")
        self.chk_builder_mode.setChecked(True)
        self.chk_builder_mode.setStyleSheet("font-weight: bold; color: #0055aa;")
        self.chk_builder_mode.stateChanged.connect(self.render_hud)
        right_layout.addWidget(self.chk_builder_mode)

        self.props_group = QGroupBox("Texture Crop Properties")
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
        
        self.btn_remove = QPushButton("Remove Element from Viewer")
        self.btn_remove.setStyleSheet("background-color: #D32F2F; color: white; font-weight: bold;")
        self.btn_remove.clicked.connect(self.remove_selected_element)
        form_layout.addRow(self.btn_remove)

        self.props_group.setLayout(form_layout)
        right_layout.addWidget(self.props_group)

        bg_group = QGroupBox("Custom Background Image")
        bg_layout = QFormLayout()
        self.btn_load_bg = QPushButton("Load Background Image...")
        self.btn_load_bg.clicked.connect(self.load_background)
        bg_layout.addRow(self.btn_load_bg)
        
        self.bg_opacity_slider = QSlider(Qt.Horizontal)
        self.bg_opacity_slider.setRange(0, 100)
        self.bg_opacity_slider.setValue(100)
        self.bg_opacity_slider.valueChanged.connect(self.update_bg_settings)
        bg_layout.addRow("Opacity:", self.bg_opacity_slider)
        
        self.bg_fade_slider = QSlider(Qt.Horizontal)
        self.bg_fade_slider.setRange(0, 100)
        self.bg_fade_slider.setValue(0)
        self.bg_fade_slider.valueChanged.connect(self.update_bg_settings)
        bg_layout.addRow("Fade to Top:", self.bg_fade_slider)
        bg_group.setLayout(bg_layout)
        right_layout.addWidget(bg_group)

        layout_group = QGroupBox("Layout Memory")
        layout_btn_layout = QHBoxLayout()
        btn_save_layout = QPushButton("💾 Save Layout")
        btn_save_layout.clicked.connect(self.save_layout)
        layout_btn_layout.addWidget(btn_save_layout)
        
        btn_load_layout = QPushButton("📂 Load Layout")
        btn_load_layout.clicked.connect(self.load_saved_layout)
        layout_btn_layout.addWidget(btn_load_layout)
        layout_group.setLayout(layout_btn_layout)
        right_layout.addWidget(layout_group)

        btn_export = QPushButton("📷 Export HUD as PNG")
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
        self.main_splitter.addWidget(right_panel)
        self.main_splitter.setSizes([300, 850, 350])
        main_layout.addWidget(self.main_splitter)

    def update_time(self):
        self.time_label.setText(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def update_bg_settings(self):
        self.bg_opacity = self.bg_opacity_slider.value()
        self.bg_fade = self.bg_fade_slider.value()
        self.render_hud()

    def on_sprite_dragged(self, sprite_name, new_x, new_y):
        if sprite_name in self.active_layout:
            self.active_layout[sprite_name] = (new_x, new_y)

    # ------------------------------------------------------------------
    # Layout Memory
    # ------------------------------------------------------------------
    def save_layout(self):
        try:
            serializable_layout = {k: list(v) for k, v in self.active_layout.items()}
            
            # 1. Main persistent location
            with open(config.LAYOUT_SAVE_FILE, 'w') as f:
                json.dump(serializable_layout, f, indent=4)
                
            # 2. Current output folder
            output_json_path = os.path.join(config.OUTPUT_DIR, "hud_layout.json")
            with open(output_json_path, 'w') as f:
                json.dump(serializable_layout, f, indent=4)
                
            # 3. Timestamped backup
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_json_name = f"hud_layout_{timestamp}.json"
            backup_json_path = os.path.join(config.HUD_LAYOUTS_DIR, backup_json_name)
            with open(backup_json_path, 'w') as f:
                json.dump(serializable_layout, f, indent=4)
                
            QMessageBox.information(self, "Saved", 
                f"Layout saved successfully!\n\n"
                f"• Main file: {os.path.basename(config.LAYOUT_SAVE_FILE)}\n"
                f"• Session output folder\n"
                f"• hud_layouts/{backup_json_name}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save layout:\n{e}")

    def load_saved_layout(self):
        if os.path.exists(config.LAYOUT_SAVE_FILE):
            try:
                with open(config.LAYOUT_SAVE_FILE, 'r') as f:
                    data = json.load(f)
                    self.active_layout = {k: tuple(v) for k, v in data.items()}
                if self.game_root:
                    self.render_hud()
            except Exception as e:
                print(f"Could not load layout: {e}")

    # ------------------------------------------------------------------
    # Loading Logic
    # ------------------------------------------------------------------
    def select_game_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Game Root Folder")
        if folder and os.path.isdir(os.path.join(folder, "data")):
            self.game_root = folder
            self.folder_entry.setText(folder)
            self.load_all_campaign_xmls()

    def load_all_campaign_xmls(self):
        if not self.game_root: return
            
        self.xml_readers.clear()
        self.all_available_sprites.clear()
        self.assets.clear_cache()
        self.texture_table.setRowCount(0)
        self.texture_table.setSortingEnabled(False)
        
        culture = self.culture_combo.currentText().lower()
        required_xmls = ["strat3.sd.xml", "shared2.sd.xml", "radar.sd.xml"]
        loaded_count = 0
        
        for xml_name in required_xmls:
            paths = [
                os.path.join(self.game_root, "data", "ui", "roman", "interface", xml_name),
                os.path.join(self.game_root, "data", "ui", culture, "interface", xml_name),
                os.path.join(self.game_root, "data", "ui", "roman", xml_name),
                os.path.join(self.game_root, "data", "ui", culture, xml_name),
                os.path.join(self.game_root, "data", "ui", xml_name)
            ]
            for p in paths:
                if os.path.exists(p):
                    try:
                        reader = SDXMLReader(p)
                        self.xml_readers[xml_name] = reader
                        loaded_count += 1
                        
                        for sprite in reader.sprites:
                            self.all_available_sprites.append((sprite, reader))
                            
                            row = self.texture_table.rowCount()
                            self.texture_table.insertRow(row)
                            
                            page = reader.pages[sprite.page_index]
                            tga_path = self.assets.get_image_path(self.game_root, culture, page.file_name)
                            icon = self.assets.get_thumbnail(tga_path, sprite.x, sprite.y, sprite.w, sprite.h)
                            
                            item_name = QTableWidgetItem(sprite.name)
                            item_name.setIcon(icon)
                            item_name.setData(Qt.UserRole, (sprite, reader)) 
                            self.texture_table.setItem(row, 0, item_name)
                            
                            item_file = QTableWidgetItem(os.path.basename(p))
                            self.texture_table.setItem(row, 1, item_file)
                            
                            item_x = QTableWidgetItem()
                            item_x.setData(Qt.DisplayRole, sprite.x)
                            self.texture_table.setItem(row, 2, item_x)
                            
                            item_y = QTableWidgetItem()
                            item_y.setData(Qt.DisplayRole, sprite.y)
                            self.texture_table.setItem(row, 3, item_y)
                            
                    except Exception as e:
                        pass
                    break
                    
        self.texture_table.setSortingEnabled(True)
        self.texture_table.setColumnWidth(0, 180)
        self.texture_table.setColumnHidden(4, True)
        
        if loaded_count > 0:
            self.status_label.setText(f"Loaded {loaded_count} HUD files.")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
            self.render_hud()
        else:
            self.status_label.setText("Error: Missing HUD XMLs.")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")

    def load_background(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Background Image", "", "Images (*.png *.jpg *.bmp *.tga)")
        if file_path:
            self.bg_image_path = file_path
            self.render_hud()

    # ------------------------------------------------------------------
    # Dynamic Layout Logic
    # ------------------------------------------------------------------
    def add_from_browser(self, item):
        data = item.data(Qt.UserRole)
        if not data: return
        sprite, reader = data
        sprite_name = sprite.name
        
        if sprite_name not in self.active_layout:
            self.active_layout[sprite_name] = (100, 100) 
            self.render_hud()
        
        for r in self.sprite_rects:
            if hasattr(r, 'sprite_data') and r.sprite_data.name == sprite_name:
                r.setSelected(True)
                break

    def remove_selected_element(self):
        if self.selected_sprite and self.selected_sprite.name in self.active_layout:
            del self.active_layout[self.selected_sprite.name]
            self.selected_sprite = None
            self.props_group.setEnabled(False)
            self.render_hud()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def draw_sprite_by_name(self, name, x, y):
        for sprite, reader in self.all_available_sprites:
            if sprite.name == name:
                culture = self.culture_combo.currentText().lower()
                tga_path = self.assets.get_image_path(self.game_root, culture, reader.pages[sprite.page_index].file_name)
                if tga_path:
                    try:
                        img = self.assets.load_image(tga_path)
                        crop = img.crop((sprite.x, sprite.y, sprite.x + sprite.w, sprite.y + sprite.h))
                        data = crop.tobytes("raw", "RGBA")
                        qim = QImage(data, crop.width, crop.height, QImage.Format_RGBA8888)
                        pix_item = self.scene.addPixmap(QPixmap.fromImage(qim))
                        pix_item.setPos(x, y)
                        return sprite.w, sprite.h
                    except Exception: pass
        return 0, 0

    def render_hud(self):
        self.scene.clear()
        self.sprite_rects.clear()
        self.props_group.setEnabled(False)
        culture = self.culture_combo.currentText().lower()

        is_builder = self.chk_builder_mode.isChecked()

        # 1. Base Background (Custom Image or Solid Green)
        if self.bg_image_path and os.path.exists(self.bg_image_path):
            try:
                bg_img = Image.open(self.bg_image_path).convert("RGBA")
                bg_img = bg_img.resize((1024, 768), Image.Resampling.LANCZOS)
                
                alpha = bg_img.split()[3]
                alpha = alpha.point(lambda p: p * (self.bg_opacity / 100.0))
                bg_img.putalpha(alpha)
                
                if self.bg_fade > 0:
                    fade_mask = Image.new('L', (1024, 768), 0)
                    draw = ImageDraw.Draw(fade_mask)
                    fade_height = int(768 * (self.bg_fade / 100.0))
                    for y in range(768):
                        if y > 768 - fade_height:
                            alpha_val = 255
                        else:
                            alpha_val = int(255 * (y / max(1, (768 - fade_height))))
                        draw.line([(0, y), (1024, y)], fill=alpha_val)
                    
                    bg_alpha = bg_img.split()[3]
                    new_alpha = Image.composite(Image.new('L', (1024, 768), 0), bg_alpha, fade_mask)
                    bg_img.putalpha(new_alpha)

                data = bg_img.tobytes("raw", "RGBA")
                qim = QImage(data, bg_img.width, bg_img.height, QImage.Format_RGBA8888)
                self.scene.addPixmap(QPixmap.fromImage(qim))
            except Exception as e:
                self.scene.addRect(0, 0, 1024, 768, QPen(Qt.NoPen), QBrush(QColor("#2b3b22")))
        else:
            self.scene.addRect(0, 0, 1024, 768, QPen(Qt.NoPen), QBrush(QColor("#2b3b22")))

        # 2. Draw Main HUD Panels (Backgrounds)
        for sprite, reader in self.all_available_sprites:
            if sprite.name in self.active_layout and sprite.name in config.BACKGROUNDS:
                draw_x, draw_y = self.active_layout[sprite.name]
                tga_path = self.assets.get_image_path(self.game_root, culture, reader.pages[sprite.page_index].file_name)
                
                if tga_path:
                    try:
                        img = self.assets.load_image(tga_path)
                        crop = img.crop((sprite.x, sprite.y, sprite.x + sprite.w, sprite.y + sprite.h))
                        data = crop.tobytes("raw", "RGBA")
                        qim = QImage(data, crop.width, crop.height, QImage.Format_RGBA8888)
                        pix_item = self.scene.addPixmap(QPixmap.fromImage(qim))
                        pix_item.setPos(draw_x, draw_y)
                    except Exception: pass

                rect = DraggableSprite(draw_x, draw_y, sprite.w, sprite.h, sprite.name, self.on_sprite_dragged)
                rect.setPen(QPen(Qt.NoPen))
                rect.sprite_data = sprite
                rect.reader_ref = reader 
                
                if is_builder:
                    rect.setFlag(QGraphicsRectItem.ItemIsMovable, True)
                    rect.setCursor(Qt.OpenHandCursor)
                    
                self.scene.addItem(rect)
                self.sprite_rects.append(rect)

        # 3. Minimap (Drawn on top of Left Panel)
        map_path = self.assets.get_image_path(self.game_root, culture, "radar_map2.tga")
        if map_path:
            try:
                img = Image.open(map_path).convert("RGBA")
                img = img.resize((210, 150), Image.Resampling.LANCZOS)
                data = img.tobytes("raw", "RGBA")
                qim = QImage(data, img.width, img.height, QImage.Format_RGBA8888)
                pix_item = self.scene.addPixmap(QPixmap.fromImage(qim))
                pix_item.setPos(31, 593) 
            except Exception: pass

        # 4. Draw Standard Elements (Buttons, etc)
        sprites_to_draw = []
        for sprite, reader in self.all_available_sprites:
            if sprite.name in self.active_layout and sprite.name in config.DRAW_ORDER:
                sprites_to_draw.append((sprite, reader))

        sprites_to_draw.sort(key=lambda item: config.DRAW_ORDER.index(item[0].name) if item[0].name in config.DRAW_ORDER else 999)

        for sprite, reader in sprites_to_draw:
            draw_x, draw_y = self.active_layout[sprite.name]
            tga_path = self.assets.get_image_path(self.game_root, culture, reader.pages[sprite.page_index].file_name)
            
            if tga_path:
                try:
                    img = self.assets.load_image(tga_path)
                    crop = img.crop((sprite.x, sprite.y, sprite.x + sprite.w, sprite.y + sprite.h))
                    data = crop.tobytes("raw", "RGBA")
                    qim = QImage(data, crop.width, crop.height, QImage.Format_RGBA8888)
                    pix_item = self.scene.addPixmap(QPixmap.fromImage(qim))
                    pix_item.setPos(draw_x, draw_y)
                except Exception: pass

            rect = DraggableSprite(draw_x, draw_y, sprite.w, sprite.h, sprite.name, self.on_sprite_dragged)
            rect.setPen(QPen(Qt.NoPen))
            rect.sprite_data = sprite
            rect.reader_ref = reader 
            
            if is_builder:
                rect.setFlag(QGraphicsRectItem.ItemIsMovable, True)
                rect.setCursor(Qt.OpenHandCursor)
                
            self.scene.addItem(rect)
            self.sprite_rects.append(rect)

        # 5. ASSEMBLE TABS dynamically
        tab_data = [
            ("TAB_ARMY_ASSEMBLY", "Army", True),
            ("TAB_TOWN_ASSEMBLY", "Town", False),
            ("TAB_AGENTS_ASSEMBLY", "Agents", False)
        ]

        tab_font = QFont("Times New Roman", 11, QFont.Bold)

        for tab_key, text, is_selected in tab_data:
            if tab_key in self.active_layout:
                tx, ty = self.active_layout[tab_key]
                
                if is_selected:
                    l_name, m_name, r_name = "HUD_TEXT_TAB_LEFT_SELECTED", "HUD_TEXT_TAB_MID_SELECTED", "HUD_TEXT_TAB_RIGHT_SELECTED"
                else:
                    l_name, m_name, r_name = "HUD_TEXT_TAB_LEFT", "HUD_TEXT_TAB_MID", "HUD_TEXT_TAB_RIGHT"
                
                lw, lh = self.draw_sprite_by_name(l_name, tx, ty)
                mw, mh = self.draw_sprite_by_name(m_name, tx + lw, ty)
                rw, rh = self.draw_sprite_by_name(r_name, tx + lw + mw, ty)
                
                total_w = lw + mw + rw
                total_h = max(lh, mh, rh) if max(lh, mh, rh) > 0 else 25
                
                if total_w > 0:
                    text_item = self.scene.addText(text, tab_font)
                    text_item.setDefaultTextColor(QColor("#221100") if not is_selected else QColor("#000000"))
                    
                    text_rect = text_item.boundingRect()
                    text_x = tx + (total_w - text_rect.width()) / 2
                    text_y = ty + (total_h - text_rect.height()) / 2 - 2
                    text_item.setPos(text_x, text_y)
                
                rect = DraggableSprite(tx, ty, total_w, total_h, tab_key, self.on_sprite_dragged)
                rect.setPen(QPen(Qt.NoPen))
                
                class DummySprite:
                    def __init__(self, name, w, h):
                        self.name, self.x, self.y, self.w, self.h = name, 0, 0, w, h
                
                rect.sprite_data = DummySprite(tab_key, total_w, total_h)
                rect.reader_ref = None
                
                if is_builder:
                    rect.setFlag(QGraphicsRectItem.ItemIsMovable, True)
                    rect.setCursor(Qt.OpenHandCursor)
                    
                self.scene.addItem(rect)
                self.sprite_rects.append(rect)

        self.scene.selectionChanged.connect(self.on_selection_changed)
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
            return

        rect_item = None
        for item in selected_items:
            if isinstance(item, QGraphicsRectItem):
                rect_item = item
                break
                
        if not rect_item or not hasattr(rect_item, 'sprite_data'): return

        self.selected_sprite = rect_item.sprite_data
        self.current_reader = rect_item.reader_ref
        
        self.props_group.setEnabled(True)
        self.name_label.setText(self.selected_sprite.name)
        
        if self.current_reader:
            self.source_label.setText(os.path.basename(self.current_reader.filepath))
            for spin in [self.x_spin, self.y_spin, self.w_spin, self.h_spin]: spin.blockSignals(True)
            self.x_spin.setValue(self.selected_sprite.x)
            self.y_spin.setValue(self.selected_sprite.y)
            self.w_spin.setValue(self.selected_sprite.w)
            self.h_spin.setValue(self.selected_sprite.h)
            for spin in [self.x_spin, self.y_spin, self.w_spin, self.h_spin]: spin.blockSignals(False)
        else:
            self.source_label.setText("Assembled Tab")
            for spin in [self.x_spin, self.y_spin, self.w_spin, self.h_spin]: spin.blockSignals(True)
            self.x_spin.setValue(0)
            self.y_spin.setValue(0)
            self.w_spin.setValue(self.selected_sprite.w)
            self.h_spin.setValue(self.selected_sprite.h)
            for spin in [self.x_spin, self.y_spin, self.w_spin, self.h_spin]: spin.blockSignals(False)

        rect_item.setPen(QPen(QColor("red"), 2))

    def update_sprite(self):
        if not self.selected_sprite or not self.current_reader: return
        self.selected_sprite.x = self.x_spin.value()
        self.selected_sprite.y = self.y_spin.value()
        self.selected_sprite.w = self.w_spin.value()
        self.selected_sprite.h = self.h_spin.value()
        self.render_hud()

    # ------------------------------------------------------------------
    # Exporting and Saving
    # ------------------------------------------------------------------
    def export_hud_image(self):
        for r in self.sprite_rects: r.setPen(QPen(Qt.NoPen))

        rect = QRectF(0, 0, 1024, 768)
        image = QImage(1024, 768, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        
        painter = QPainter(image)
        self.scene.render(painter, rect, rect)
        painter.end()

        default_path = os.path.join(config.OUTPUT_DIR, "campaign_hud_preview.png")
        file_path, _ = QFileDialog.getSaveFileName(self, "Save HUD Image", default_path, "PNG Image (*.png)")
        
        if file_path:
            image.save(file_path)
            QMessageBox.information(self, "Exported", f"HUD image saved to:\n{file_path}")

    def take_program_screenshot(self):
        default_name = f"program_screenshot_{datetime.now().strftime('%H%M%S')}.png"
        default_path = os.path.join(config.OUTPUT_DIR, default_name)
        
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Program Screenshot", default_path, "PNG Image (*.png)")
        
        if file_path:
            pixmap = self.grab()
            pixmap.save(file_path)
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
            QMessageBox.information(self, "Saved", f"Saved changes to:\n{', '.join(saved_files)}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save file:\n{e}")