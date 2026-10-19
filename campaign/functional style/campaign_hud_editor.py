#!/usr/bin/env python3
"""
RTW Campaign HUD Visual Assembler
Functional Core, Imperative Shell (PyQt).
"""

import os
import shutil
import json
from datetime import datetime
from dataclasses import dataclass, replace
from typing import Tuple, Dict, List, Optional
from types import MappingProxyType

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

# --- IMMUTABLE STATE (Functional Core) ---

@dataclass(frozen=True)
class AppState:
    game_root: str = ""
    xml_data: MappingProxyType = MappingProxyType({})
    all_sprites: Tuple[Tuple[sd_xml_parser.SpriteElement, Tuple[sd_xml_parser.SpritePage, ...]], ...] = ()
    active_layout: MappingProxyType = config.DEFAULT_LAYOUT
    selected_sprite: Optional[sd_xml_parser.SpriteElement] = None
    current_reader: Optional[tuple] = None
    bg_image_path: str = ""
    bg_opacity: int = 100
    bg_fade: int = 0

# --- PURE FUNCTIONS ---

def update_layout_position(layout: Dict[str, Tuple[int, int]], sprite_name: str, x: int, y: int) -> MappingProxyType:
    new_layout = dict(layout)
    new_layout[sprite_name] = (x, y)
    return MappingProxyType(new_layout)

def remove_layout_element(layout: Dict[str, Tuple[int, int]], sprite_name: str) -> MappingProxyType:
    new_layout = dict(layout)
    if sprite_name in new_layout:
        del new_layout[sprite_name]
    return MappingProxyType(new_layout)

def filter_sprites_in_layout(all_sprites, layout, draw_order=None) -> List[tuple]:
    filtered = [
        (spr, reader) for spr, reader in all_sprites 
        if spr.name in layout and (draw_order is None or spr.name in draw_order)
    ]
    if draw_order:
        order_dict = {name: i for i, name in enumerate(draw_order)}
        filtered.sort(key=lambda item: order_dict.get(item[0].name, 999))
    return filtered

def merge_layouts(saved_data: dict, default_layout: dict) -> MappingProxyType:
    merged = dict(default_layout)
    merged.update({k: tuple(v) for k, v in saved_data.items()})
    return MappingProxyType(merged)

# --- IMPERATIVE SHELL (PyQt UI & File I/O) ---

def update_ui_time(window):
    window.time_label.setText(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

def on_sprite_dragged(window, sprite_name, new_x, new_y):
    new_layout = update_layout_position(window.app_state.active_layout, sprite_name, new_x, new_y)
    window.app_state = replace(window.app_state, active_layout=new_layout)

def select_game_folder(window):
    folder = QFileDialog.getExistingDirectory(window, "Select Game Root Folder")
    if folder and os.path.isdir(os.path.join(folder, "data")):
        window.app_state = replace(window.app_state, game_root=folder)
        window.folder_entry.setText(folder)
        load_all_campaign_xmls(window)

def load_background(window):
    file_path, _ = QFileDialog.getOpenFileName(window, "Select Background Image", "", "Images (*.png *.jpg *.bmp *.tga)")
    if file_path:
        window.app_state = replace(window.app_state, bg_image_path=file_path)
        render_hud(window)

def reset_layout(window):
    window.app_state = replace(window.app_state, active_layout=config.DEFAULT_LAYOUT)
    if os.path.exists(config.LAYOUT_SAVE_FILE):
        os.remove(config.LAYOUT_SAVE_FILE)
    render_hud(window)

def save_layout(window):
    try:
        serializable_layout = {k: list(v) for k, v in window.app_state.active_layout.items()}
        
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

def load_all_campaign_xmls(window):
    state = window.app_state
    if not state.game_root: return
        
    window.texture_table.setRowCount(0)
    window.texture_table.setSortingEnabled(False)
    
    culture = window.culture_combo.currentText().lower()
    required_xmls = ("strat3.sd.xml", "shared2.sd.xml", "radar.sd.xml")
    
    loaded_xml = {}
    loaded_sprites = []
    
    for xml_name in required_xmls:
        paths = (
            os.path.join(state.game_root, "data", "ui", "roman", "interface", xml_name),
            os.path.join(state.game_root, "data", "ui", culture, "interface", xml_name),
            os.path.join(state.game_root, "data", "ui", "roman", xml_name),
            os.path.join(state.game_root, "data", "ui", culture, xml_name),
            os.path.join(state.game_root, "data", "ui", xml_name)
        )
        for p in paths:
            if os.path.exists(p):
                try:
                    pages, sprites, root, filepath = sd_xml_parser.parse_sd_xml(p)
                    reader_data = (pages, sprites, root, filepath)
                    loaded_xml[xml_name] = reader_data
                    
                    for sprite in sprites:
                        loaded_sprites.append((sprite, reader_data))
                        
                        row = window.texture_table.rowCount()
                        window.texture_table.insertRow(row)
                        
                        page = pages[sprite.page_index]
                        tga_path = asset_manager.get_image_path(state.game_root, culture, page.file_name)
                        icon = asset_manager.get_thumbnail(tga_path, sprite.x, sprite.y, sprite.w, sprite.h)
                        
                        item_name = QTableWidgetItem(sprite.name)
                        item_name.setIcon(icon)
                        item_name.setData(Qt.UserRole, (sprite, reader_data)) 
                        window.texture_table.setItem(row, 0, item_name)
                        
                        item_file = QTableWidgetItem(os.path.basename(p))
                        window.texture_table.setItem(row, 1, item_file)
                        
                        item_x = QTableWidgetItem()
                        item_x.setData(Qt.DisplayRole, sprite.x)
                        window.texture_table.setItem(row, 2, item_x)
                        
                        item_y = QTableWidgetItem()
                        item_y.setData(Qt.DisplayRole, sprite.y)
                        window.texture_table.setItem(row, 3, item_y)
                        
                except Exception as e:
                    print(f"Error parsing {p}: {e}")
                break
                
    window.texture_table.setSortingEnabled(True)
    window.texture_table.setColumnWidth(0, 180)
    
    if loaded_xml:
        window.status_label.setText(f"Loaded {len(loaded_xml)} HUD files.")
        window.status_label.setStyleSheet("color: green; font-weight: bold;")
        
        window.app_state = replace(
            window.app_state, 
            xml_data=MappingProxyType(loaded_xml),
            all_sprites=tuple(loaded_sprites)
        )
        render_hud(window)
    else:
        window.status_label.setText("Error: Missing HUD XMLs.")
        window.status_label.setStyleSheet("color: red; font-weight: bold;")

def render_hud(window):
    try:
        window.scene.clear()
        window.props_group.setEnabled(False)
        
        state = window.app_state
        culture = window.culture_combo.currentText().lower()
        is_builder = window.chk_builder_mode.isChecked()

        # 1. Base Background
        if state.bg_image_path and os.path.exists(state.bg_image_path):
            try:
                bg_img = Image.open(state.bg_image_path).convert("RGBA")
                bg_img = bg_img.resize((1024, 768), Image.Resampling.LANCZOS)
                
                alpha = bg_img.split()[3]
                alpha = alpha.point(lambda p: p * (state.bg_opacity / 100.0))
                bg_img.putalpha(alpha)
                
                if state.bg_fade > 0:
                    fade_mask = Image.new('L', (1024, 768), 0)
                    draw = ImageDraw.Draw(fade_mask)
                    fade_height = int(768 * (state.bg_fade / 100.0))
                    for y in range(768):
                        alpha_val = 255 if y > 768 - fade_height else int(255 * (y / max(1, (768 - fade_height))))
                        draw.line([(0, y), (1024, y)], fill=alpha_val)
                    
                    bg_alpha = bg_img.split()[3]
                    new_alpha = Image.composite(Image.new('L', (1024, 768), 0), bg_alpha, fade_mask)
                    bg_img.putalpha(new_alpha)

                data = bg_img.tobytes("raw", "RGBA")
                qim = QImage(data, bg_img.width, bg_img.height, QImage.Format_RGBA8888)
                window.scene.addPixmap(QPixmap.fromImage(qim))
            except Exception as e:
                print(f"Background Error: {e}")
                window.scene.addRect(0, 0, 1024, 768, QPen(Qt.NoPen), QBrush(QColor("#2b3b22")))
        else:
            window.scene.addRect(0, 0, 1024, 768, QPen(Qt.NoPen), QBrush(QColor("#2b3b22")))

        # Helper to render a single sprite block
        def add_sprite_to_scene(sprite, draw_x, draw_y):
            rect = DraggableSprite(draw_x, draw_y, sprite.w, sprite.h, sprite.name, lambda n, x, y: on_sprite_dragged(window, n, x, y))
            rect.setPen(QPen(Qt.NoPen))
            rect.sprite_data = sprite
            if is_builder:
                rect.setFlag(QGraphicsRectItem.ItemIsMovable, True)
                rect.setCursor(Qt.OpenHandCursor)
            window.scene.addItem(rect)

        # 2. Main Background Panels
        bg_sprites = filter_sprites_in_layout(state.all_sprites, state.active_layout, config.BACKGROUNDS)
        for sprite, reader in bg_sprites:
            draw_x, draw_y = state.active_layout[sprite.name]
            page = reader[0][sprite.page_index]
            tga_path = asset_manager.get_image_path(state.game_root, culture, page.file_name)
            
            if tga_path:
                img = asset_manager.load_image_cached(tga_path)
                if img:
                    crop = img.crop((sprite.x, sprite.y, sprite.x + sprite.w, sprite.y + sprite.h))
                    data = crop.tobytes("raw", "RGBA")
                    qim = QImage(data, crop.width, crop.height, QImage.Format_RGBA8888)
                    pix_item = window.scene.addPixmap(QPixmap.fromImage(qim))
                    pix_item.setPos(draw_x, draw_y)

            add_sprite_to_scene(sprite, draw_x, draw_y)

        # 3. Minimap
        map_path = asset_manager.get_image_path(state.game_root, culture, "radar_map2.tga")
        if map_path:
            img = asset_manager.load_image_cached(map_path)
            if img:
                img = img.resize((210, 150), Image.Resampling.LANCZOS)
                data = img.tobytes("raw", "RGBA")
                qim = QImage(data, img.width, img.height, QImage.Format_RGBA8888)
                pix_item = window.scene.addPixmap(QPixmap.fromImage(qim))
                pix_item.setPos(31, 593) 

        # 4. Standard Elements (Build, Train, End Turn, etc.)
        std_sprites = filter_sprites_in_layout(state.all_sprites, state.active_layout, config.DRAW_ORDER)
        for sprite, reader in std_sprites:
            draw_x, draw_y = state.active_layout[sprite.name]
            page = reader[0][sprite.page_index]
            tga_path = asset_manager.get_image_path(state.game_root, culture, page.file_name)
            
            if tga_path:
                img = asset_manager.load_image_cached(tga_path)
                if img:
                    crop = img.crop((sprite.x, sprite.y, sprite.x + sprite.w, sprite.y + sprite.h))
                    data = crop.tobytes("raw", "RGBA")
                    qim = QImage(data, crop.width, crop.height, QImage.Format_RGBA8888)
                    pix_item = window.scene.addPixmap(QPixmap.fromImage(qim))
                    pix_item.setPos(draw_x, draw_y)

            add_sprite_to_scene(sprite, draw_x, draw_y)

        # 5. Tabs
        tab_data = (
            ("TAB_ARMY_ASSEMBLY", "Army", True),
            ("TAB_TOWN_ASSEMBLY", "Town", False),
            ("TAB_AGENTS_ASSEMBLY", "Agents", False)
        )
        tab_font = QFont("Times New Roman", 11, QFont.Bold)

        def draw_tab_part(name, x, y):
            sprites = [s for s, r in state.all_sprites if s.name == name]
            if not sprites: return 0, 0
            sprite = sprites[0]
            page = next(r[0][sprite.page_index] for s, r in state.all_sprites if s.name == name)
            tga_path = asset_manager.get_image_path(state.game_root, culture, page.file_name)
            if tga_path:
                img = asset_manager.load_image_cached(tga_path)
                if img:
                    crop = img.crop((sprite.x, sprite.y, sprite.x + sprite.w, sprite.y + sprite.h))
                    data = crop.tobytes("raw", "RGBA")
                    qim = QImage(data, crop.width, crop.height, QImage.Format_RGBA8888)
                    pix_item = window.scene.addPixmap(QPixmap.fromImage(qim))
                    pix_item.setPos(x, y)
                    return sprite.w, sprite.h
            return 0, 0

        for tab_key, text, is_selected in tab_data:
            if tab_key in state.active_layout:
                tx, ty = state.active_layout[tab_key]
                
                if is_selected:
                    l, m, r = "HUD_TEXT_TAB_LEFT_SELECTED", "HUD_TEXT_TAB_MID_SELECTED", "HUD_TEXT_TAB_RIGHT_SELECTED"
                else:
                    l, m, r = "HUD_TEXT_TAB_LEFT", "HUD_TEXT_TAB_MID", "HUD_TEXT_TAB_RIGHT"
                
                lw, lh = draw_tab_part(l, tx, ty)
                mw, mh = draw_tab_part(m, tx + lw, ty)
                rw, rh = draw_tab_part(r, tx + lw + mw, ty)
                
                total_w = lw + mw + rw
                total_h = max(lh, mh, rh) if max(lh, mh, rh) > 0 else 25
                
                if total_w > 0:
                    text_item = window.scene.addText(text, tab_font)
                    text_item.setDefaultTextColor(QColor("#221100") if not is_selected else QColor("#000000"))
                    text_rect = text_item.boundingRect()
                    text_item.setPos(tx + (total_w - text_rect.width()) / 2, ty + (total_h - text_rect.height()) / 2 - 2)
                
                rect = DraggableSprite(tx, ty, total_w, total_h, tab_key, lambda n, x, y: on_sprite_dragged(window, n, x, y))
                rect.setPen(QPen(Qt.NoPen))
                rect.sprite_data = {"name": tab_key, "x": 0, "y": 0, "w": total_w, "h": total_h}
                if is_builder:
                    rect.setFlag(QGraphicsRectItem.ItemIsMovable, True)
                    rect.setCursor(Qt.OpenHandCursor)
                window.scene.addItem(rect)

        window.view.fitInView(window.view.sceneRect(), Qt.KeepAspectRatio)
    except Exception as e:
        print(f"CRITICAL RENDER ERROR: {e}")

def on_selection_changed(window):
    try:
        for item in window.scene.items():
            if isinstance(item, DraggableSprite):
                item.setPen(QPen(Qt.NoPen))

        selected = window.scene.selectedItems()
        if not selected:
            window.props_group.setEnabled(False)
            window.app_state = replace(window.app_state, selected_sprite=None)
            return

        rect_item = next((item for item in selected if isinstance(item, DraggableSprite)), None)
        if not rect_item: return

        sprite_data = rect_item.sprite_data
        
        if isinstance(sprite_data, dict):
            window.name_label.setText(sprite_data["name"])
            window.source_label.setText("Assembled Tab")
            window.x_spin.setValue(0)
            window.y_spin.setValue(0)
            window.w_spin.setValue(sprite_data["w"])
            window.h_spin.setValue(sprite_data["h"])
            window.props_group.setEnabled(True)
            rect_item.setPen(QPen(QColor("red"), 2))
            return

        window.app_state = replace(window.app_state, selected_sprite=sprite_data)
        window.props_group.setEnabled(True)
        window.name_label.setText(sprite_data.name)
        
        reader = next((r for s, r in window.app_state.all_sprites if s.name == sprite_data.name), None)
        if reader:
            window.source_label.setText(os.path.basename(reader[3]))
            for spin in (window.x_spin, window.y_spin, window.w_spin, window.h_spin): spin.blockSignals(True)
            window.x_spin.setValue(sprite_data.x)
            window.y_spin.setValue(sprite_data.y)
            window.w_spin.setValue(sprite_data.w)
            window.h_spin.setValue(sprite_data.h)
            for spin in (window.x_spin, window.y_spin, window.w_spin, window.h_spin): spin.blockSignals(False)

        rect_item.setPen(QPen(QColor("red"), 2))
    except RuntimeError:
        # Safely ignore the error when the app is closing and C++ objects are deleted
        pass

def update_sprite(window):
    state = window.app_state
    if not state.selected_sprite: return
    
    new_sprite = replace(state.selected_sprite, 
                         x=window.x_spin.value(), 
                         y=window.y_spin.value(), 
                         w=window.w_spin.value(), 
                         h=window.h_spin.value())
    
    if new_sprite.element_ref is not None:
        new_sprite.element_ref.set("x", str(new_sprite.x))
        new_sprite.element_ref.set("y", str(new_sprite.y))
        new_sprite.element_ref.set("w", str(new_sprite.w))
        new_sprite.element_ref.set("h", str(new_sprite.h))
        
    new_all_sprites = tuple(
        (new_sprite if s.name == new_sprite.name else s, r) 
        for s, r in state.all_sprites
    )
    
    window.app_state = replace(state, all_sprites=new_all_sprites, selected_sprite=new_sprite)
    render_hud(window)

def remove_selected_element(window):
    state = window.app_state
    if not state.selected_sprite: return
    
    new_layout = remove_layout_element(state.active_layout, state.selected_sprite.name)
    window.app_state = replace(state, active_layout=new_layout, selected_sprite=None)
    window.props_group.setEnabled(False)
    render_hud(window)

def load_saved_layout(window):
    if os.path.exists(config.LAYOUT_SAVE_FILE):
        try:
            with open(config.LAYOUT_SAVE_FILE, 'r') as f:
                data = json.load(f)
            merged_layout = merge_layouts(data, config.DEFAULT_LAYOUT)
            window.app_state = replace(window.app_state, active_layout=merged_layout)
            if window.app_state.game_root:
                render_hud(window)
        except Exception as e:
            print(f"Could not load layout: {e}")

def export_hud_image(window):
    state = window.app_state
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
    state = window.app_state
    if not state.xml_data: return
    
    saved_files = []
    try:
        for xml_name, reader in state.xml_data.items():
            pages, sprites, root, filepath = reader
            backup = filepath + ".bak"
            shutil.copy2(filepath, backup)
            sd_xml_parser.save_sd_xml(root, sprites, filepath)
            saved_files.append(xml_name)
        QMessageBox.information(window, "Saved", f"Saved changes to:\n{', '.join(saved_files)}")
    except Exception as e:
        QMessageBox.critical(window, "Error", f"Could not save file:\n{e}")

# --- UI SETUP ---

def create_main_window():
    window = QMainWindow()
    window.app_state = AppState() # Initialize Immutable State
    
    window.setWindowTitle("RTW Campaign HUD Editor (Functional)")
    window.resize(1600, 950)

    central = QWidget()
    window.setCentralWidget(central)
    main_layout = QVBoxLayout(central)
    main_layout.setContentsMargins(0, 0, 0, 0)
    main_layout.setSpacing(0)

    # Top Bar
    top_bar_widget = QWidget()
    top_bar_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed) 
    top_bar = QHBoxLayout(top_bar_widget)
    top_bar.setContentsMargins(5, 5, 5, 5)
    
    window.folder_entry = QLineEdit(readOnly=True)
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
    top_bar.addWidget(window.status_label)

    window.time_label = QLabel()
    top_bar.addWidget(window.time_label)
    timer = QTimer(window)
    timer.timeout.connect(lambda: update_ui_time(window))
    timer.start(1000)

    main_layout.addWidget(top_bar_widget, 0) 

    # Splitter
    splitter = QSplitter(Qt.Horizontal)
    splitter.setChildrenCollapsible(False) 
    
    # Left Panel
    left_panel = QWidget()
    left_layout = QVBoxLayout(left_panel)
    left_layout.setContentsMargins(5, 5, 5, 5)
    window.texture_table = QTableWidget(0, 5)
    window.texture_table.setHorizontalHeaderLabels(["Preview", "Name", "File", "X", "Y"])
    window.texture_table.setSortingEnabled(True)
    left_layout.addWidget(window.texture_table)
    splitter.addWidget(left_panel)

    # Center Panel
    window.scene = QGraphicsScene()
    window.view = QGraphicsView(window.scene)
    window.view.setRenderHint(QPainter.Antialiasing)
    window.view.setBackgroundBrush(QBrush(QColor("#1e1e1e")))
    window.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    window.view.setSceneRect(0, 0, 1024, 768)
    window.view.setDragMode(QGraphicsView.ScrollHandDrag)
    window.view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
    
    window.scene.selectionChanged.connect(lambda: on_selection_changed(window))
    
    splitter.addWidget(window.view)

    # Right Panel
    right_panel = QWidget()
    right_layout = QVBoxLayout(right_panel)
    right_layout.setContentsMargins(5, 5, 5, 5)

    window.chk_builder_mode = QCheckBox("Builder Mode")
    window.chk_builder_mode.setChecked(True)
    window.chk_builder_mode.stateChanged.connect(lambda: render_hud(window))
    right_layout.addWidget(window.chk_builder_mode)

    window.props_group = QGroupBox("Properties")
    form = QFormLayout()
    window.name_label = QLabel("-")
    window.source_label = QLabel("-")
    window.x_spin = QSpinBox()
    window.y_spin = QSpinBox()
    window.w_spin = QSpinBox()
    window.h_spin = QSpinBox()
    for spin in (window.x_spin, window.y_spin, window.w_spin, window.h_spin):
        spin.setRange(-9999, 9999)
        spin.valueChanged.connect(lambda: update_sprite(window))
    form.addRow("Name:", window.name_label)
    form.addRow("Source:", window.source_label)
    form.addRow("X:", window.x_spin)
    form.addRow("Y:", window.y_spin)
    form.addRow("W:", window.w_spin)
    form.addRow("H:", window.h_spin)
    window.props_group.setLayout(form)
    right_layout.addWidget(window.props_group)

    # Remove Element Button
    btn_remove = QPushButton("Remove Element from Viewer")
    btn_remove.setStyleSheet("background-color: #D32F2F; color: white; font-weight: bold;")
    btn_remove.clicked.connect(lambda: remove_selected_element(window))
    right_layout.addWidget(btn_remove)

    # Background Settings
    bg_group = QGroupBox("Background")
    bg_form = QFormLayout()
    
    btn_load_bg = QPushButton("Load Background Image...")
    btn_load_bg.clicked.connect(lambda: load_background(window))
    bg_form.addRow(btn_load_bg)
    
    window.bg_opacity_slider = QSlider(Qt.Horizontal)
    window.bg_opacity_slider.setRange(0, 100)
    window.bg_opacity_slider.setValue(100)
    
    def update_bg_state():
        window.app_state = replace(window.app_state, bg_opacity=window.bg_opacity_slider.value())
        render_hud(window)
        
    window.bg_opacity_slider.valueChanged.connect(update_bg_state)
    bg_form.addRow("Opacity:", window.bg_opacity_slider)
    bg_group.setLayout(bg_form)
    right_layout.addWidget(bg_group)

    # Layout Memory Buttons
    layout_btn_layout = QHBoxLayout()
    btn_save_layout = QPushButton("💾 Save Layout")
    btn_save_layout.clicked.connect(lambda: save_layout(window))
    layout_btn_layout.addWidget(btn_save_layout)
    
    btn_load_layout = QPushButton("📂 Load Layout")
    btn_load_layout.clicked.connect(lambda: load_saved_layout(window))
    layout_btn_layout.addWidget(btn_load_layout)
    right_layout.addLayout(layout_btn_layout)

    # Reset Layout Button
    btn_reset_layout = QPushButton("🔄 Reset Layout to Default")
    btn_reset_layout.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold;")
    btn_reset_layout.clicked.connect(lambda: reset_layout(window))
    right_layout.addWidget(btn_reset_layout)

    # Export & Save Buttons
    btn_export = QPushButton("📷 Export HUD as PNG")
    btn_export.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 5px;")
    btn_export.clicked.connect(lambda: export_hud_image(window))
    right_layout.addWidget(btn_export)

    btn_screenshot = QPushButton("📸 Screenshot Program UI")
    btn_screenshot.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 5px;")
    btn_screenshot.clicked.connect(lambda: take_program_screenshot(window))
    right_layout.addWidget(btn_screenshot)

    btn_save_xml = QPushButton("Save Changes to XML Files")
    btn_save_xml.clicked.connect(lambda: save_all_xmls(window))
    right_layout.addWidget(btn_save_xml)

    right_layout.addStretch()
    
    splitter.addWidget(right_panel)
    splitter.setSizes([300, 850, 350])
    main_layout.addWidget(splitter, 1) 

    load_saved_layout(window)
    return window