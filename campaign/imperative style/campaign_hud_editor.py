#!/usr/bin/env python3
"""
RTW Campaign HUD Visual Assembler
Procedural Application Logic.
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

import config
import sd_xml_parser
import asset_manager
from canvas_items import DraggableSprite

# Global State Dictionary (Replaces 'self')
STATE = {
    "game_root": "",
    "xml_data": {},          # filename -> parsed data
    "all_sprites": [],       # list of (sprite_dict, reader_data)
    "active_layout": dict(config.DEFAULT_LAYOUT),
    "selected_sprite": None,
    "current_reader": None,
    "sprite_rects": [],
    "bg_image_path": None,
    "bg_opacity": 100,
    "bg_fade": 0
}

def update_time(window):
    window.time_label.setText(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

def update_bg_settings(window):
    STATE["bg_opacity"] = window.bg_opacity_slider.value()
    STATE["bg_fade"] = window.bg_fade_slider.value()
    render_hud(window)

def on_sprite_dragged(sprite_name, new_x, new_y):
    if sprite_name in STATE["active_layout"]:
        STATE["active_layout"][sprite_name] = (new_x, new_y)

def select_game_folder(window):
    folder = QFileDialog.getExistingDirectory(window, "Select Game Root Folder")
    if folder and os.path.isdir(os.path.join(folder, "data")):
        STATE["game_root"] = folder
        window.folder_entry.setText(folder)
        load_all_campaign_xmls(window)

def load_all_campaign_xmls(window):
    if not STATE["game_root"]: return
        
    STATE["xml_data"].clear()
    STATE["all_sprites"].clear()
    asset_manager.clear_cache()
    window.texture_table.setRowCount(0)
    window.texture_table.setSortingEnabled(False)
    
    culture = window.culture_combo.currentText().lower()
    required_xmls = ["strat3.sd.xml", "shared2.sd.xml", "radar.sd.xml"]
    loaded_count = 0
    
    for xml_name in required_xmls:
        paths = [
            os.path.join(STATE["game_root"], "data", "ui", "roman", "interface", xml_name),
            os.path.join(STATE["game_root"], "data", "ui", culture, "interface", xml_name),
            os.path.join(STATE["game_root"], "data", "ui", "roman", xml_name),
            os.path.join(STATE["game_root"], "data", "ui", culture, xml_name),
            os.path.join(STATE["game_root"], "data", "ui", xml_name)
        ]
        for p in paths:
            if os.path.exists(p):
                try:
                    reader = sd_xml_parser.parse_sd_xml(p)
                    STATE["xml_data"][xml_name] = reader
                    loaded_count += 1
                    
                    for sprite in reader["sprites"]:
                        STATE["all_sprites"].append((sprite, reader))
                        
                        row = window.texture_table.rowCount()
                        window.texture_table.insertRow(row)
                        
                        page = reader["pages"][sprite["page_index"]]
                        tga_path = asset_manager.get_image_path(STATE["game_root"], culture, page["file_name"])
                        icon = asset_manager.get_thumbnail(tga_path, sprite["x"], sprite["y"], sprite["w"], sprite["h"])
                        
                        item_name = QTableWidgetItem(sprite["name"])
                        item_name.setIcon(icon)
                        item_name.setData(Qt.UserRole, (sprite, reader)) 
                        window.texture_table.setItem(row, 0, item_name)
                        
                        item_file = QTableWidgetItem(os.path.basename(p))
                        window.texture_table.setItem(row, 1, item_file)
                        
                        item_x = QTableWidgetItem()
                        item_x.setData(Qt.DisplayRole, sprite["x"])
                        window.texture_table.setItem(row, 2, item_x)
                        
                        item_y = QTableWidgetItem()
                        item_y.setData(Qt.DisplayRole, sprite["y"])
                        window.texture_table.setItem(row, 3, item_y)
                        
                except Exception as e:
                    pass
                break
                
    window.texture_table.setSortingEnabled(True)
    window.texture_table.setColumnWidth(0, 180)
    window.texture_table.setColumnHidden(4, True)
    
    if loaded_count > 0:
        window.status_label.setText(f"Loaded {loaded_count} HUD files.")
        window.status_label.setStyleSheet("color: green; font-weight: bold;")
        render_hud(window)
    else:
        window.status_label.setText("Error: Missing HUD XMLs.")
        window.status_label.setStyleSheet("color: red; font-weight: bold;")

def load_background(window):
    file_path, _ = QFileDialog.getOpenFileName(window, "Select Background Image", "", "Images (*.png *.jpg *.bmp *.tga)")
    if file_path:
        STATE["bg_image_path"] = file_path
        render_hud(window)

def add_from_browser(window, item):
    data = item.data(Qt.UserRole)
    if not data: return
    sprite, reader = data
    sprite_name = sprite["name"]
    
    if sprite_name not in STATE["active_layout"]:
        STATE["active_layout"][sprite_name] = (100, 100) 
        render_hud(window)
    
    for r in STATE["sprite_rects"]:
        if hasattr(r, 'sprite_data') and r.sprite_data["name"] == sprite_name:
            r.setSelected(True)
            break

def remove_selected_element(window):
    if STATE["selected_sprite"] and STATE["selected_sprite"]["name"] in STATE["active_layout"]:
        del STATE["active_layout"][STATE["selected_sprite"]["name"]]
        STATE["selected_sprite"] = None
        window.props_group.setEnabled(False)
        render_hud(window)

def draw_sprite_by_name(window, name, x, y):
    culture = window.culture_combo.currentText().lower()
    for sprite, reader in STATE["all_sprites"]:
        if sprite["name"] == name:
            tga_path = asset_manager.get_image_path(STATE["game_root"], culture, reader["pages"][sprite["page_index"]]["file_name"])
            if tga_path:
                try:
                    img = asset_manager.load_image(tga_path)
                    crop = img.crop((sprite["x"], sprite["y"], sprite["x"] + sprite["w"], sprite["y"] + sprite["h"]))
                    data = crop.tobytes("raw", "RGBA")
                    qim = QImage(data, crop.width, crop.height, QImage.Format_RGBA8888)
                    pix_item = window.scene.addPixmap(QPixmap.fromImage(qim))
                    pix_item.setPos(x, y)
                    return sprite["w"], sprite["h"]
                except Exception: pass
    return 0, 0

def render_hud(window):
    STATE["sprite_rects"].clear()
    window.scene.clear()
    window.props_group.setEnabled(False)
    culture = window.culture_combo.currentText().lower()
    is_builder = window.chk_builder_mode.isChecked()

    # 1. Base Background
    if STATE["bg_image_path"] and os.path.exists(STATE["bg_image_path"]):
        try:
            bg_img = Image.open(STATE["bg_image_path"]).convert("RGBA")
            bg_img = bg_img.resize((1024, 768), Image.Resampling.LANCZOS)
            
            alpha = bg_img.split()[3]
            alpha = alpha.point(lambda p: p * (STATE["bg_opacity"] / 100.0))
            bg_img.putalpha(alpha)
            
            if STATE["bg_fade"] > 0:
                fade_mask = Image.new('L', (1024, 768), 0)
                draw = ImageDraw.Draw(fade_mask)
                fade_height = int(768 * (STATE["bg_fade"] / 100.0))
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
            window.scene.addPixmap(QPixmap.fromImage(qim))
        except Exception as e:
            window.scene.addRect(0, 0, 1024, 768, QPen(Qt.NoPen), QBrush(QColor("#2b3b22")))
    else:
        window.scene.addRect(0, 0, 1024, 768, QPen(Qt.NoPen), QBrush(QColor("#2b3b22")))

    # 2. Main HUD Panels
    for sprite, reader in STATE["all_sprites"]:
        if sprite["name"] in STATE["active_layout"] and sprite["name"] in config.BACKGROUNDS:
            draw_x, draw_y = STATE["active_layout"][sprite["name"]]
            tga_path = asset_manager.get_image_path(STATE["game_root"], culture, reader["pages"][sprite["page_index"]]["file_name"])
            
            if tga_path:
                try:
                    img = asset_manager.load_image(tga_path)
                    crop = img.crop((sprite["x"], sprite["y"], sprite["x"] + sprite["w"], sprite["y"] + sprite["h"]))
                    data = crop.tobytes("raw", "RGBA")
                    qim = QImage(data, crop.width, crop.height, QImage.Format_RGBA8888)
                    pix_item = window.scene.addPixmap(QPixmap.fromImage(qim))
                    pix_item.setPos(draw_x, draw_y)
                except Exception: pass

            rect = DraggableSprite(draw_x, draw_y, sprite["w"], sprite["h"], sprite["name"], on_sprite_dragged)
            rect.setPen(QPen(Qt.NoPen))
            rect.sprite_data = sprite
            rect.reader_ref = reader 
            
            if is_builder:
                rect.setFlag(QGraphicsRectItem.ItemIsMovable, True)
                rect.setCursor(Qt.OpenHandCursor)
                
            window.scene.addItem(rect)
            STATE["sprite_rects"].append(rect)

    # 3. Minimap
    map_path = asset_manager.get_image_path(STATE["game_root"], culture, "radar_map2.tga")
    if map_path:
        try:
            img = Image.open(map_path).convert("RGBA")
            img = img.resize((210, 150), Image.Resampling.LANCZOS)
            data = img.tobytes("raw", "RGBA")
            qim = QImage(data, img.width, img.height, QImage.Format_RGBA8888)
            pix_item = window.scene.addPixmap(QPixmap.fromImage(qim))
            pix_item.setPos(31, 593) 
        except Exception: pass

    # 4. Standard Elements
    sprites_to_draw = []
    for sprite, reader in STATE["all_sprites"]:
        if sprite["name"] in STATE["active_layout"] and sprite["name"] in config.DRAW_ORDER:
            sprites_to_draw.append((sprite, reader))

    sprites_to_draw.sort(key=lambda item: config.DRAW_ORDER.index(item[0]["name"]) if item[0]["name"] in config.DRAW_ORDER else 999)

    for sprite, reader in sprites_to_draw:
        draw_x, draw_y = STATE["active_layout"][sprite["name"]]
        tga_path = asset_manager.get_image_path(STATE["game_root"], culture, reader["pages"][sprite["page_index"]]["file_name"])
        
        if tga_path:
            try:
                img = asset_manager.load_image(tga_path)
                crop = img.crop((sprite["x"], sprite["y"], sprite["x"] + sprite["w"], sprite["y"] + sprite["h"]))
                data = crop.tobytes("raw", "RGBA")
                qim = QImage(data, crop.width, crop.height, QImage.Format_RGBA8888)
                pix_item = window.scene.addPixmap(QPixmap.fromImage(qim))
                pix_item.setPos(draw_x, draw_y)
            except Exception: pass

        rect = DraggableSprite(draw_x, draw_y, sprite["w"], sprite["h"], sprite["name"], on_sprite_dragged)
        rect.setPen(QPen(Qt.NoPen))
        rect.sprite_data = sprite
        rect.reader_ref = reader 
        
        if is_builder:
            rect.setFlag(QGraphicsRectItem.ItemIsMovable, True)
            rect.setCursor(Qt.OpenHandCursor)
            
        window.scene.addItem(rect)
        STATE["sprite_rects"].append(rect)

    # 5. Tabs
    tab_data = [
        ("TAB_ARMY_ASSEMBLY", "Army", True),
        ("TAB_TOWN_ASSEMBLY", "Town", False),
        ("TAB_AGENTS_ASSEMBLY", "Agents", False)
    ]

    tab_font = QFont("Times New Roman", 11, QFont.Bold)

    for tab_key, text, is_selected in tab_data:
        if tab_key in STATE["active_layout"]:
            tx, ty = STATE["active_layout"][tab_key]
            
            if is_selected:
                l_name, m_name, r_name = "HUD_TEXT_TAB_LEFT_SELECTED", "HUD_TEXT_TAB_MID_SELECTED", "HUD_TEXT_TAB_RIGHT_SELECTED"
            else:
                l_name, m_name, r_name = "HUD_TEXT_TAB_LEFT", "HUD_TEXT_TAB_MID", "HUD_TEXT_TAB_RIGHT"
            
            lw, lh = draw_sprite_by_name(window, l_name, tx, ty)
            mw, mh = draw_sprite_by_name(window, m_name, tx + lw, ty)
            rw, rh = draw_sprite_by_name(window, r_name, tx + lw + mw, ty)
            
            total_w = lw + mw + rw
            total_h = max(lh, mh, rh) if max(lh, mh, rh) > 0 else 25
            
            if total_w > 0:
                text_item = window.scene.addText(text, tab_font)
                text_item.setDefaultTextColor(QColor("#221100") if not is_selected else QColor("#000000"))
                
                text_rect = text_item.boundingRect()
                text_x = tx + (total_w - text_rect.width()) / 2
                text_y = ty + (total_h - text_rect.height()) / 2 - 2
                text_item.setPos(text_x, text_y)
            
            rect = DraggableSprite(tx, ty, total_w, total_h, tab_key, on_sprite_dragged)
            rect.setPen(QPen(Qt.NoPen))
            
            # Create a dictionary to mimic the sprite_data object
            rect.sprite_data = {"name": tab_key, "x": 0, "y": 0, "w": total_w, "h": total_h}
            rect.reader_ref = None
            
            if is_builder:
                rect.setFlag(QGraphicsRectItem.ItemIsMovable, True)
                rect.setCursor(Qt.OpenHandCursor)
                
            window.scene.addItem(rect)
            STATE["sprite_rects"].append(rect)

    window.scene.selectionChanged.connect(lambda: on_selection_changed(window))
    window.view.fitInView(window.view.sceneRect(), Qt.KeepAspectRatio)

def on_selection_changed(window):
    for r in STATE["sprite_rects"]: r.setPen(QPen(Qt.NoPen))

    selected_items = window.scene.selectedItems()
    if not selected_items:
        window.props_group.setEnabled(False)
        STATE["selected_sprite"] = None
        return

    rect_item = None
    for item in selected_items:
        if isinstance(item, QGraphicsRectItem):
            rect_item = item
            break
            
    if not rect_item or not hasattr(rect_item, 'sprite_data'): return

    STATE["selected_sprite"] = rect_item.sprite_data
    STATE["current_reader"] = rect_item.reader_ref
    
    window.props_group.setEnabled(True)
    window.name_label.setText(STATE["selected_sprite"]["name"])
    
    if STATE["current_reader"]:
        window.source_label.setText(os.path.basename(STATE["current_reader"]["filepath"]))
        for spin in [window.x_spin, window.y_spin, window.w_spin, window.h_spin]: spin.blockSignals(True)
        window.x_spin.setValue(STATE["selected_sprite"]["x"])
        window.y_spin.setValue(STATE["selected_sprite"]["y"])
        window.w_spin.setValue(STATE["selected_sprite"]["w"])
        window.h_spin.setValue(STATE["selected_sprite"]["h"])
        for spin in [window.x_spin, window.y_spin, window.w_spin, window.h_spin]: spin.blockSignals(False)
    else:
        window.source_label.setText("Assembled Tab")
        for spin in [window.x_spin, window.y_spin, window.w_spin, window.h_spin]: spin.blockSignals(True)
        window.x_spin.setValue(0)
        window.y_spin.setValue(0)
        window.w_spin.setValue(STATE["selected_sprite"]["w"])
        window.h_spin.setValue(STATE["selected_sprite"]["h"])
        for spin in [window.x_spin, window.y_spin, window.w_spin, window.h_spin]: spin.blockSignals(False)

    rect_item.setPen(QPen(QColor("red"), 2))

def update_sprite(window):
    if not STATE["selected_sprite"] or not STATE["current_reader"]: return
    STATE["selected_sprite"]["x"] = window.x_spin.value()
    STATE["selected_sprite"]["y"] = window.y_spin.value()
    STATE["selected_sprite"]["w"] = window.w_spin.value()
    STATE["selected_sprite"]["h"] = window.h_spin.value()
    render_hud(window)

def save_layout(window):
    try:
        serializable_layout = {k: list(v) for k, v in STATE["active_layout"].items()}
        
        with open(config.LAYOUT_SAVE_FILE, 'w') as f:
            json.dump(serializable_layout, f, indent=4)
            
        output_json_path = os.path.join(config.OUTPUT_DIR, "hud_layout.json")
        with open(output_json_path, 'w') as f:
            json.dump(serializable_layout, f, indent=4)
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_json_name = f"hud_layout_{timestamp}.json"
        backup_json_path = os.path.join(config.HUD_LAYOUTS_DIR, backup_json_name)
        with open(backup_json_path, 'w') as f:
            json.dump(serializable_layout, f, indent=4)
            
        QMessageBox.information(window, "Saved", 
            f"Layout saved successfully!\n\n"
            f"• Main file: {os.path.basename(config.LAYOUT_SAVE_FILE)}\n"
            f"• Session output folder\n"
            f"• hud_layouts/{backup_json_name}")
    except Exception as e:
        QMessageBox.critical(window, "Error", f"Could not save layout:\n{e}")

def load_saved_layout(window):
    if os.path.exists(config.LAYOUT_SAVE_FILE):
        try:
            with open(config.LAYOUT_SAVE_FILE, 'r') as f:
                data = json.load(f)
                STATE["active_layout"] = {k: tuple(v) for k, v in data.items()}
            if STATE["game_root"]:
                render_hud(window)
        except Exception as e:
            print(f"Could not load layout: {e}")

def export_hud_image(window):
    for r in STATE["sprite_rects"]: r.setPen(QPen(Qt.NoPen))

    rect = QRectF(0, 0, 1024, 768)
    image = QImage(1024, 768, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    
    painter = QPainter(image)
    window.scene.render(painter, rect, rect)
    painter.end()

    default_path = os.path.join(config.OUTPUT_DIR, "campaign_hud_preview.png")
    file_path, _ = QFileDialog.getSaveFileName(window, "Save HUD Image", default_path, "PNG Image (*.png)")
    
    if file_path:
        image.save(file_path)
        QMessageBox.information(window, "Exported", f"HUD image saved to:\n{file_path}")

def take_program_screenshot(window):
    default_name = f"program_screenshot_{datetime.now().strftime('%H%M%S')}.png"
    default_path = os.path.join(config.OUTPUT_DIR, default_name)
    
    file_path, _ = QFileDialog.getSaveFileName(window, "Save Program Screenshot", default_path, "PNG Image (*.png)")
    
    if file_path:
        pixmap = window.grab()
        pixmap.save(file_path)
        QMessageBox.information(window, "Saved", f"Program screenshot saved to:\n{file_path}")

def save_all_xmls(window):
    if not STATE["xml_data"]: return
    saved_files = []
    try:
        for xml_name, reader in STATE["xml_data"].items():
            backup = reader["filepath"] + ".bak"
            shutil.copy2(reader["filepath"], backup)
            sd_xml_parser.save_sd_xml(reader)
            saved_files.append(xml_name)
        QMessageBox.information(window, "Saved", f"Saved changes to:\n{', '.join(saved_files)}")
    except Exception as e:
        QMessageBox.critical(window, "Error", f"Could not save file:\n{e}")

def create_main_window():
    """Builds and configures the QMainWindow."""
    window = QMainWindow()
    window.setWindowTitle("RTW Campaign HUD Editor (Visual)")
    window.resize(1600, 950)

    central = QWidget()
    window.setCentralWidget(central)
    main_layout = QVBoxLayout(central)

    # --- TOP BAR ---
    top_bar_widget = QWidget()
    top_bar_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    top_bar = QHBoxLayout(top_bar_widget)
    top_bar.setContentsMargins(0, 0, 0, 0)
    
    window.folder_entry = QLineEdit()
    window.folder_entry.setReadOnly(True)
    window.folder_entry.setPlaceholderText("Select RTW game folder...")
    top_bar.addWidget(window.folder_entry)

    btn_browse = QPushButton("Browse Game Folder")
    btn_browse.clicked.connect(lambda: select_game_folder(window))
    top_bar.addWidget(btn_browse)

    window.culture_combo = QComboBox()
    window.culture_combo.addItems(["Roman", "Greek", "Eastern", "Barbarian", "Carthaginian", "Egyptian"])
    window.culture_combo.currentTextChanged.connect(lambda: load_all_campaign_xmls(window))
    top_bar.addWidget(QLabel("Culture:"))
    top_bar.addWidget(window.culture_combo)

    window.status_label = QLabel("Please select your RTW folder.")
    window.status_label.setStyleSheet("color: orange; font-weight: bold;")
    top_bar.addWidget(window.status_label)

    window.time_label = QLabel()
    window.time_label.setStyleSheet("color: #333; font-weight: bold; padding-left: 10px;")
    top_bar.addWidget(window.time_label)
    
    timer = QTimer(window)
    timer.timeout.connect(lambda: update_time(window))
    timer.start(1000)
    update_time(window)

    main_layout.addWidget(top_bar_widget)

    # --- MAIN SPLITTER ---
    main_splitter = QSplitter(Qt.Horizontal)
    main_splitter.setChildrenCollapsible(False)

    # 1. Left Panel: Texture Browser
    left_panel = QWidget()
    left_layout = QVBoxLayout(left_panel)
    left_layout.setContentsMargins(0, 0, 0, 0)
    left_layout.addWidget(QLabel("<b>Texture Browser</b> (Double-click to add)"))
    
    window.texture_table = QTableWidget()
    window.texture_table.setColumnCount(5)
    window.texture_table.setHorizontalHeaderLabels(["Preview", "Name", "File", "X", "Y"])
    window.texture_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
    window.texture_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
    window.texture_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
    window.texture_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
    window.texture_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
    window.texture_table.setSelectionBehavior(QAbstractItemView.SelectRows)
    window.texture_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    window.texture_table.setSortingEnabled(True)
    window.texture_table.verticalHeader().setVisible(False)
    window.texture_table.itemDoubleClicked.connect(lambda item: add_from_browser(window, item))
    left_layout.addWidget(window.texture_table)
    
    main_splitter.addWidget(left_panel)

    # 2. Center Panel: Canvas
    window.scene = QGraphicsScene()
    window.view = QGraphicsView(window.scene)
    window.view.setRenderHint(QPainter.Antialiasing)
    window.view.setBackgroundBrush(QBrush(QColor("#1e1e1e")))
    window.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    window.view.setSceneRect(0, 0, 1024, 768)
    window.view.setDragMode(QGraphicsView.ScrollHandDrag)
    window.view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
    main_splitter.addWidget(window.view)

    # 3. Right Panel: Properties & Controls
    right_panel = QWidget()
    right_panel.setMinimumWidth(350)
    right_panel.setMaximumWidth(500)
    right_layout = QVBoxLayout(right_panel)

    window.chk_builder_mode = QCheckBox("HUD Builder Mode (Drag & Drop)")
    window.chk_builder_mode.setChecked(True)
    window.chk_builder_mode.setStyleSheet("font-weight: bold; color: #0055aa;")
    window.chk_builder_mode.stateChanged.connect(lambda: render_hud(window))
    right_layout.addWidget(window.chk_builder_mode)

    window.props_group = QGroupBox("Texture Crop Properties")
    window.props_group.setEnabled(False)
    form_layout = QFormLayout()

    window.name_label = QLabel("-")
    window.source_label = QLabel("-")
    window.x_spin = QSpinBox()
    window.y_spin = QSpinBox()
    window.w_spin = QSpinBox()
    window.h_spin = QSpinBox()

    for spin in [window.x_spin, window.y_spin, window.w_spin, window.h_spin]:
        spin.setRange(-9999, 9999)
        spin.valueChanged.connect(lambda: update_sprite(window))

    form_layout.addRow("Name:", window.name_label)
    form_layout.addRow("Source XML:", window.source_label)
    form_layout.addRow("Crop X:", window.x_spin)
    form_layout.addRow("Crop Y:", window.y_spin)
    form_layout.addRow("Width:", window.w_spin)
    form_layout.addRow("Height:", window.h_spin)
    
    window.btn_remove = QPushButton("Remove Element from Viewer")
    window.btn_remove.setStyleSheet("background-color: #D32F2F; color: white; font-weight: bold;")
    window.btn_remove.clicked.connect(lambda: remove_selected_element(window))
    form_layout.addRow(window.btn_remove)

    window.props_group.setLayout(form_layout)
    right_layout.addWidget(window.props_group)

    bg_group = QGroupBox("Custom Background Image")
    bg_layout = QFormLayout()
    window.btn_load_bg = QPushButton("Load Background Image...")
    window.btn_load_bg.clicked.connect(lambda: load_background(window))
    bg_layout.addRow(window.btn_load_bg)
    
    window.bg_opacity_slider = QSlider(Qt.Horizontal)
    window.bg_opacity_slider.setRange(0, 100)
    window.bg_opacity_slider.setValue(100)
    window.bg_opacity_slider.valueChanged.connect(lambda: update_bg_settings(window))
    bg_layout.addRow("Opacity:", window.bg_opacity_slider)
    
    window.bg_fade_slider = QSlider(Qt.Horizontal)
    window.bg_fade_slider.setRange(0, 100)
    window.bg_fade_slider.setValue(0)
    window.bg_fade_slider.valueChanged.connect(lambda: update_bg_settings(window))
    bg_layout.addRow("Fade to Top:", window.bg_fade_slider)
    bg_group.setLayout(bg_layout)
    right_layout.addWidget(bg_group)

    layout_group = QGroupBox("Layout Memory")
    layout_btn_layout = QHBoxLayout()
    btn_save_layout = QPushButton("💾 Save Layout")
    btn_save_layout.clicked.connect(lambda: save_layout(window))
    layout_btn_layout.addWidget(btn_save_layout)
    
    btn_load_layout = QPushButton("📂 Load Layout")
    btn_load_layout.clicked.connect(lambda: load_saved_layout(window))
    layout_btn_layout.addWidget(btn_load_layout)
    layout_group.setLayout(layout_btn_layout)
    right_layout.addWidget(layout_group)

    btn_export = QPushButton("📷 Export HUD as PNG")
    btn_export.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 5px;")
    btn_export.clicked.connect(lambda: export_hud_image(window))
    right_layout.addWidget(btn_export)

    btn_screenshot = QPushButton("📸 Screenshot Program UI")
    btn_screenshot.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 5px;")
    btn_screenshot.clicked.connect(lambda: take_program_screenshot(window))
    right_layout.addWidget(btn_screenshot)

    btn_save = QPushButton("Save Changes to XML Files")
    btn_save.clicked.connect(lambda: save_all_xmls(window))
    right_layout.addWidget(btn_save)

    right_layout.addStretch()
    main_splitter.addWidget(right_panel)
    main_splitter.setSizes([300, 850, 350])
    main_layout.addWidget(main_splitter)

    # Load initial layout state
    load_saved_layout(window)
    return window