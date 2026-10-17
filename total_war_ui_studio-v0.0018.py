#!/usr/bin/env python3
"""
RTW Sprite & HUD Studio
=======================
For Rome: Total War (original, BI, Alexander, REX patch).

Five tabs:
  • Sprites   — browse every sprite in the loaded .sd.xml with thumbnails
  • Atlases   — view the TGA atlas with sprite boxes drawn; drag a box to
                 repack its coordinates in the .sd.xml
  • HUD Mockup — plan a HUD layout visually on a 1024x768 canvas
                 (reference only — does not affect the in-game HUD)
  • Menu (LNT) — view and edit menu screen layouts from a .lnt file.
                 Renders each piece's actual artwork from the .tga files
                 referenced by the LNT's own <texture> blocks, and draws
                 text pieces with a gold serif look matching the game.

Quick start: click "Pick mod folder…" and point at your mod folder
(e.g. test_projects/project1).  The tool will find the .lnt, the .sd.xml
packs, the .tga files under data/menu/ and data/menu/textures/, and the
<texture> blocks inside the .lnt itself.

Key facts:
  • .sd.xml x/y/w/h are ATLAS coordinates, not on-screen positions.
  • .lnt <UI piece> x/y/w/h ARE real on-screen positions for menu screens.
  • .lnt <texture> blocks name individual .tga files (in data/menu/ or
    data/menu/textures/) and their named sub-regions; the tool crops
    those regions and uses them to render the LNT canvas.
  • Campaign/battle HUD positions are hard-coded in the game executable.

Requirements: Python 3.8+, Pillow  (pip install pillow)
"""

import json
import re as _re
import shutil
import tkinter as tk
import xml.etree.ElementTree as ET
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

try:
    import tkinter.font as _tkfont
except Exception:
    _tkfont = None

try:
    from PIL import Image, ImageTk
    RESAMPLE = getattr(Image, "Resampling", Image).LANCZOS
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    Image = ImageTk = None
    RESAMPLE = None

APP = "RTW Sprite & HUD Studio"
VERSION = "v18"
HUD_W, HUD_H = 1024, 768

# Preferred serif fonts, tried in order — the first one present on the
# system wins.  Anything missing just falls back to Tk's default.
SERIF_FAMILIES = (
    "Trajan Pro", "Palatino Linotype", "Palatino", "Garamond",
    "Georgia", "Times New Roman", "Nimbus Roman", "Liberation Serif",
    "DejaVu Serif", "FreeSerif", "serif",
)

# Gold-ish colour for menu text — approximates the cream/gold used in RTW.
MENU_TEXT_COLOR = "#ecd9a8"
MENU_TEXT_SHADOW = "#5a4420"


# ---------------------------------------------------------------------------
#  Data model
# ---------------------------------------------------------------------------
class Sprite:
    __slots__ = ("name", "page", "x", "y", "w", "h", "crop", "element")

    def __init__(self, name, page, x, y, w, h, crop, element):
        self.name = name
        self.page = page
        self.x, self.y, self.w, self.h = x, y, w, h
        self.crop = crop
        self.element = element


class SDXml:
    """A parsed .sd.xml file, with atlas TGA images attached."""

    atlas_search_dirs = []

    def __init__(self, path):
        self.path = Path(path)
        self.tree = ET.parse(path)
        self.root = self.tree.getroot()
        self.sprites = []
        self.atlases = {}
        self._load()

    def _find_atlas(self, filename):
        rel = filename.replace("\\", "/").lstrip("/")
        name = Path(rel).name

        for d in SDXml.atlas_search_dirs:
            for cand in (d / name, d / rel, d / "interface" / name):
                if cand.is_file():
                    try:
                        return Image.open(cand).convert("RGBA")
                    except Exception:
                        pass

        base = self.path.parent
        candidates = [base / name]
        p = base
        for _ in range(8):
            candidates.append(p / name)
            candidates.append(p / "interface" / name)
            candidates.append(p / "roman" / "interface" / name)
            candidates.append(p / "ui" / "roman" / "interface" / name)
            candidates.append(p / "ui" / "interface" / name)
            candidates.append(p / rel)
            if p == p.parent:
                break
            p = p.parent
        if base.name.lower() == "interface":
            cultures_dir = base.parent
            if cultures_dir.is_dir():
                for culture in cultures_dir.iterdir():
                    if culture.is_dir():
                        candidates.append(culture / "interface" / name)
        seen = set()
        for c in candidates:
            key = str(c).lower()
            if key in seen:
                continue
            seen.add(key)
            if c.is_file():
                try:
                    return Image.open(c).convert("RGBA")
                except Exception:
                    pass
        return None

    def _load(self):
        if not HAS_PIL:
            return
        for page in self.root.iter("page"):
            fname = page.get("file", "")
            if fname and fname not in self.atlases:
                self.atlases[fname] = self._find_atlas(fname)
            atlas = self.atlases.get(fname)
            for sp in page.findall("sprite"):
                try:
                    x = int(sp.get("x", "0"))
                    y = int(sp.get("y", "0"))
                    w = int(sp.get("w", "1"))
                    h = int(sp.get("h", "1"))
                except ValueError:
                    continue
                crop = None
                if atlas is not None:
                    try:
                        crop = atlas.crop((x, y, x + w, y + h))
                    except Exception:
                        crop = None
                self.sprites.append(Sprite(sp.get("name", "sprite"),
                                           fname, x, y, w, h, crop, sp))

    def refresh_crop(self, sprite):
        atlas = self.atlases.get(sprite.page)
        if atlas is None:
            return
        try:
            sprite.crop = atlas.crop((sprite.x, sprite.y,
                                      sprite.x + sprite.w,
                                      sprite.y + sprite.h))
        except Exception:
            sprite.crop = None

    def save(self):
        for sp in self.sprites:
            sp.element.set("x", str(sp.x))
            sp.element.set("y", str(sp.y))
            sp.element.set("w", str(sp.w))
            sp.element.set("h", str(sp.h))
            if sp.element.get("name") != sp.name:
                sp.element.set("name", sp.name)
        self.tree.write(self.path, encoding="utf-8", xml_declaration=True)


# ---------------------------------------------------------------------------
#  LNT parser and editor
# ---------------------------------------------------------------------------
class LntFile:
    def __init__(self, path):
        self.path = Path(path)
        self.raw = self.path.read_text(encoding="utf-8", errors="replace")
        self.width = 1024
        self.height = 768
        self.pieces = []
        self.pages = []
        self.textures = {}
        self.tga_by_stem = {}
        self._parse()
        self._load_textures()

    def _parse(self):
        m = _re.search(r"<layout_width>\s*(\d+)\s*</layout_width>", self.raw)
        if m: self.width = int(m.group(1))
        m = _re.search(r"<layout_height>\s*(\d+)\s*</layout_height>", self.raw)
        if m: self.height = int(m.group(1))

        page_patterns = [
            (r'<lpage\b[^>]*\bname="([^"]+)"[^>]*>(.*?)</lpage>', 2),
            (r'<screen\b[^>]*\bname="([^"]+)"[^>]*>(.*?)</screen>', 2),
            (r'<menu\b[^>]*\bname="([^"]+)"[^>]*>(.*?)</menu>', 2),
            (r'<page\b[^>]*\bname="([^"]+)"[^>]*>(.*?)</page>', 2),
            (r'<lpage\b[^>]*>(.*?)</lpage>', 1),
            (r'<screen\b[^>]*>(.*?)</screen>', 1),
            (r'<menu\b[^>]*>(.*?)</menu>', 1),
        ]

        pieces_by_page = []
        found_wrapper = False

        def extract_name(body, fallback_idx):
            m = _re.search(r"<name>\s*([^<]+?)\s*</name>", body)
            if m and m.group(1).strip():
                return m.group(1).strip()
            m = _re.search(r"<menu_id>\s*([^<]+?)\s*</menu_id>", body)
            if m and m.group(1).strip():
                return m.group(1).strip()
            m = _re.search(r"<page_id>\s*([^<]+?)\s*</page_id>", body)
            if m and m.group(1).strip():
                return m.group(1).strip()
            m = _re.search(r"<UI piece>\s*([^\s<]+)", body)
            if m:
                return f"(page {fallback_idx}: {m.group(1)[:24]})"
            return f"(page {fallback_idx})"

        for pat, ngroups in page_patterns:
            matches = list(_re.finditer(pat, self.raw,
                                        _re.DOTALL | _re.IGNORECASE))
            if not matches:
                continue
            found_wrapper = True
            for idx, mm in enumerate(matches):
                if ngroups == 2:
                    page_name = mm.group(1).strip()
                    body = mm.group(2)
                else:
                    body = mm.group(1)
                    page_name = ""
                if not page_name:
                    page_name = extract_name(body, idx + 1)
                pieces = self._parse_pieces(body)
                if pieces:
                    pieces_by_page.append((page_name, pieces))
            break

        if not found_wrapper:
            all_pieces = self._parse_pieces(self.raw)
            by_menu = {}
            for pc in all_pieces:
                key = pc.get("menu_id") or "(no menu)"
                by_menu.setdefault(key, []).append(pc)
            if len(by_menu) > 1:
                pieces_by_page = [(k, v) for k, v in by_menu.items()]
            else:
                pieces_by_page = [("(all pieces)", all_pieces)]

        seen_names = {}
        self.pieces = []
        self.pages = []
        for pname, pieces in pieces_by_page:
            seen_names[pname] = seen_names.get(pname, 0) + 1
            if seen_names[pname] > 1:
                pname = f"{pname} #{seen_names[pname]}"
            self.pages.append(pname)
            for d in pieces:
                d["page"] = pname
                self.pieces.append(d)

    def _parse_pieces(self, body):
        pieces = []
        for pm in _re.finditer(r"<UI piece>\s*([^\s<]+)(.*?)</UI piece>",
                               body, _re.DOTALL):
            name, inner = pm.group(1), pm.group(2)
            d = {"name": name, "identifier": "", "object_id": "",
                 "x": 0, "y": 0, "w": 100, "h": 30,
                 "text": "", "menu_id": "", "page": "", "raw": pm.group(0)}
            m = _re.search(r"<identifier>\s*([^<]+)\s*</identifier>", inner)
            if m: d["identifier"] = m.group(1).strip()
            m = _re.search(r"<object_id>\s*([^<]+)\s*</object_id>", inner)
            if m: d["object_id"] = m.group(1).strip()
            m = _re.search(r"<menu_id>\s*([^<]+)\s*</menu_id>", inner)
            if m: d["menu_id"] = m.group(1).strip()
            m = _re.search(r"<UI text>\s*([^\s<]+)", inner)
            if m: d["text"] = m.group(1).strip()
            for key, tag in (("x", "x"), ("y", "y"),
                             ("w", "width"), ("h", "height")):
                m = _re.search(rf"<{tag}>\s*(\d+)\s*</{tag}>", inner)
                if m: d[key] = int(m.group(1))
            pieces.append(d)
        return pieces

    def _load_textures(self):
        """See v17 for the full explanation.  Same behaviour."""
        if not HAS_PIL:
            return
        base = self.path.parent

        tex_re = _re.compile(
            r"<texture>\s*([^<\r\n]+)(.*?)</texture>",
            _re.DOTALL | _re.IGNORECASE)
        region_re = _re.compile(
            r"<region>\s*([^\s<]+)(.*?)</region>",
            _re.DOTALL | _re.IGNORECASE)

        def _num(body, tag, default=None):
            m = _re.search(rf"<{tag}>\s*(-?\d+)\s*</{tag}>",
                           body, _re.IGNORECASE)
            return int(m.group(1)) if m else default

        image_cache = {}

        def _open(path):
            key = str(path).lower()
            if key in image_cache:
                return image_cache[key]
            try:
                img = Image.open(path).convert("RGBA")
            except Exception:
                img = None
            image_cache[key] = img
            return img

        for tex_m in tex_re.finditer(self.raw):
            tex_file = tex_m.group(1).strip().replace("\\", "/")
            tex_body = tex_m.group(2)

            path_dir = ""
            m = _re.search(r"<path>\s*([^<]+?)\s*</path>",
                           tex_body, _re.IGNORECASE)
            if m:
                path_dir = m.group(1).strip().replace("\\", "/")

            name = Path(tex_file).name
            stem = Path(tex_file).stem

            candidates = []
            if path_dir:
                candidates.append(base / path_dir / name)
            candidates.append(base / tex_file)
            candidates.append(base / name)
            for d in SDXml.atlas_search_dirs:
                if path_dir:
                    candidates.append(d / path_dir / name)
                candidates.append(d / name)
                candidates.append(d / tex_file)
                candidates.append(d / "textures" / name)
                candidates.append(d / "menu" / "textures" / name)
                candidates.append(d / "menu" / name)

            img = None
            for cand in candidates:
                if cand.is_file():
                    img = _open(cand)
                    if img is not None:
                        break
            if img is None:
                continue

            self.tga_by_stem.setdefault(stem.lower(), img)

            for reg_m in region_re.finditer(tex_body):
                region_name = reg_m.group(1).strip()
                reg_body = reg_m.group(2)
                left = _num(reg_body, "left")
                top = _num(reg_body, "top")
                right = _num(reg_body, "right")
                bottom = _num(reg_body, "bottom")
                region_img = img
                if (left is not None and top is not None
                        and right is not None and bottom is not None
                        and right > left and bottom > top):
                    try:
                        region_img = img.crop((left, top, right, bottom))
                    except Exception:
                        region_img = img
                self.textures[region_name] = region_img

        for d in SDXml.atlas_search_dirs:
            if not d.is_dir():
                continue
            try:
                for f in d.glob("*.tga"):
                    stem = f.stem.lower()
                    if stem in self.tga_by_stem:
                        continue
                    img = _open(f)
                    if img is not None:
                        self.tga_by_stem[stem] = img
            except OSError:
                pass

    def update_piece(self, piece, x=None, y=None, w=None, h=None):
        old = piece["raw"]
        new = old
        for tag, val in (("x", x if x is not None else piece["x"]),
                         ("y", y if y is not None else piece["y"]),
                         ("width", w if w is not None else piece["w"]),
                         ("height", h if h is not None else piece["h"])):
            new = _re.sub(rf"<{tag}>\s*\d+\s*</{tag}>",
                          f"<{tag}>{val}</{tag}>", new)
        if new != old:
            self.raw = self.raw.replace(old, new, 1)
            piece["raw"] = new
            if x is not None: piece["x"] = x
            if y is not None: piece["y"] = y
            if w is not None: piece["w"] = w
            if h is not None: piece["h"] = h

    def save(self):
        self.path.write_text(self.raw, encoding="utf-8")


# ---------------------------------------------------------------------------
#  Vanilla HUD reference positions (1024x768 reference grid)
# ---------------------------------------------------------------------------
VANILLA_HUD = [
    ("STRAT_HUD_LEFT",    0, 587, 281, 181),
    ("STRAT_HUD_MIDDLE", 281, 621, 462, 147),
    ("STRAT_HUD_RIGHT",  743, 587, 281, 181),
]


# ---------------------------------------------------------------------------
#  Game install / mod discovery helpers
# ---------------------------------------------------------------------------
EXE_NAMES = ("RomeTW.exe", "rometw.exe",
             "RomeTW-BI.exe", "RomeTW-ALX.exe",
             "RomeTW-ALX.exe", "alexander.exe")


def _looks_like_game_root(p):
    if not p.is_dir():
        return False
    for name in EXE_NAMES:
        if (p / name).is_file():
            return True
    try:
        for child in p.iterdir():
            if child.is_file() and child.name.lower().endswith(".exe"):
                lname = child.name.lower()
                if "rome" in lname or "alexander" in lname:
                    return True
    except OSError:
        pass
    return False


def _looks_like_data_dir(p):
    if not p.is_dir():
        return False
    hints = ("menu", "ui", "text", "world", "descr_", "packs")
    hits = 0
    for h in hints:
        if (p / h).is_dir() or (p / h).exists():
            hits += 1
    return hits >= 2


def discover_mod_folder(folder):
    folder = Path(folder).resolve()
    if not folder.is_dir():
        return None

    data_dir = None
    mod_root = None

    if (folder / "data").is_dir() and _looks_like_data_dir(folder / "data"):
        mod_root = folder
        data_dir = folder / "data"
    elif _looks_like_data_dir(folder):
        data_dir = folder
        mod_root = folder.parent
    elif _looks_like_game_root(folder) and (folder / "data").is_dir():
        mod_root = folder
        data_dir = folder / "data"
    else:
        for child in folder.iterdir():
            if child.is_dir() and (child / "data").is_dir() \
                    and _looks_like_data_dir(child / "data"):
                mod_root = child
                data_dir = child / "data"
                break

    if data_dir is None:
        return None

    install_root = None
    p = mod_root
    for _ in range(6):
        p = p.parent
        if p == p.parent:
            break
        if _looks_like_game_root(p):
            install_root = p
            break

    try:
        lnt_files = sorted(data_dir.rglob("*.lnt"))
    except OSError:
        lnt_files = []
    try:
        sd_files = sorted(data_dir.rglob("*.sd.xml"))
    except OSError:
        sd_files = []

    search_dirs = []

    def add_dir(d):
        if d.is_dir() and d not in search_dirs:
            search_dirs.append(d)

    add_dir(data_dir / "menu" / "textures")
    add_dir(data_dir / "menu" / "menu")
    add_dir(data_dir / "menu" / "sd")
    add_dir(data_dir / "menu")
    add_dir(data_dir)
    for sub in ("textures", "ui", "ui/menu"):
        add_dir(data_dir / sub)
    ui_dir = data_dir / "ui"
    if ui_dir.is_dir():
        for culture in ui_dir.iterdir():
            if culture.is_dir():
                add_dir(culture)
                add_dir(culture / "interface")
                add_dir(culture / "menu")
                add_dir(culture / "menu" / "interface")
                add_dir(culture / "textures")

    if install_root is not None:
        inst_data = install_root / "data"
        add_dir(inst_data / "menu" / "textures")
        add_dir(inst_data / "menu")
        add_dir(inst_data)
        for sub in ("textures", "ui", "ui/menu"):
            add_dir(inst_data / sub)
        inst_ui = inst_data / "ui"
        if inst_ui.is_dir():
            for culture in inst_ui.iterdir():
                if culture.is_dir():
                    add_dir(culture)
                    add_dir(culture / "interface")
                    add_dir(culture / "menu")
                    add_dir(culture / "textures")

    return {
        "mod_root": mod_root,
        "data_dir": data_dir,
        "install_root": install_root,
        "lnt_files": lnt_files,
        "sd_files": sd_files,
        "atlas_search_dirs": search_dirs,
    }


# ---------------------------------------------------------------------------
#  App
# ---------------------------------------------------------------------------
class App:
    def __init__(self, root):
        self.root = root
        root.title(f"{APP} {VERSION}")
        root.geometry("1400x900")
        root.minsize(1000, 640)

        # Pick a serif font for menu text rendering.  Missing families
        # are ignored — Tk falls back to its default if nothing matches.
        self.ui_serif = self._pick_serif_font()

        self.sdxml = None
        self.current_sprite = None
        self._filtered_indices = []
        self._preview_photo = None

        self._atlas_scale = 1.0
        self._atlas_origin = (10, 10)
        self._atlas_drag = None
        self._atlas_selected = None
        self._atlas_photo = None
        self._atlas_rects = {}

        self.mock_items = []
        self.mock_selected = None
        self.mock_drag = None
        self.mock_scale = 1.0
        self.mock_origin = (20, 20)
        self.mock_photos = []

        self.lnt_file = None
        self.lnt_selected = None
        self.lnt_drag = None
        self._lnt_photos = []

        self.mod_folder = None
        self.mod_root = None
        self.mod_data_dir = None
        self.install_root = None

        self._build_menu()
        self._build_ui()

    # ------------------------------------------------------------------
    def _pick_serif_font(self):
        """Return the name of the first available serif family, or a
        safe fallback.  Never raises."""
        if _tkfont is None:
            return "TkDefaultFont"
        try:
            families = set(_tkfont.families(self.root))
        except Exception:
            return "TkDefaultFont"
        for f in SERIF_FAMILIES:
            if f in families:
                return f
        return "TkDefaultFont"

    # ------------------------------------------------------------------
    def _build_menu(self):
        mb = tk.Menu(self.root)
        fm = tk.Menu(mb, tearoff=0)
        fm.add_command(label="Pick mod folder…",
                       accelerator="Ctrl+M", command=self.set_mod_folder)
        fm.add_separator()
        fm.add_command(label="Open .sd.xml…", command=self.open_sd)
        fm.add_command(label="Save .sd.xml (backup first)", command=self.save_sd)
        fm.add_command(label="Show loaded file info…",
                       command=self.show_file_info)
        fm.add_separator()
        fm.add_command(label="Export current atlas as TGA…",
                       command=self.export_current_atlas)
        fm.add_separator()
        fm.add_command(label="Exit", command=self.root.quit)
        mb.add_cascade(label="File", menu=fm)

        hm = tk.Menu(mb, tearoff=0)
        hm.add_command(label="How RTW UI files work", command=self.help_rtw)
        hm.add_command(label="About", command=self.about)
        mb.add_cascade(label="Help", menu=hm)
        self.root.config(menu=mb)
        self.root.bind("<Control-m>", lambda e: self.set_mod_folder())

    def _build_ui(self):
        tb = ttk.Frame(self.root, padding=(6, 4))
        tb.pack(fill="x")
        ttk.Button(tb, text="Pick mod folder…",
                   command=self.set_mod_folder).pack(side="left", padx=2)
        ttk.Separator(tb, orient="vertical").pack(side="left",
                                                   fill="y", padx=6)
        ttk.Button(tb, text="Open .sd.xml…",
                   command=self.open_sd).pack(side="left", padx=2)
        ttk.Button(tb, text="Save .sd.xml",
                   command=self.save_sd).pack(side="left", padx=2)
        ttk.Button(tb, text="File info…",
                   command=self.show_file_info).pack(side="left", padx=2)
        self.file_label = ttk.Label(tb, text="No mod loaded",
                                    foreground="#666")
        self.file_label.pack(side="right", padx=6)

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=6, pady=4)

        self._build_sprites_tab()
        self._build_atlas_tab()
        self._build_mockup_tab()
        self._build_lnt_tab()

        self.status = ttk.Label(self.root,
                                text=f"{APP} {VERSION} — Ready. "
                                     f"Start by clicking 'Pick mod folder…'.",
                                anchor="w", relief="sunken", padding=(6, 2))
        self.status.pack(fill="x", side="bottom")

    # ------------------------------------------------------------------
    #  Mod folder auto-discovery
    # ------------------------------------------------------------------
    def set_mod_folder(self):
        folder = filedialog.askdirectory(
            title="Pick your mod folder (the one containing data/)",
            initialdir=str(self.mod_folder or Path(__file__).resolve().parent))
        if not folder:
            return
        info = discover_mod_folder(folder)
        if info is None:
            messagebox.showerror(
                "Not a mod folder",
                f"Couldn't find a data/ folder under:\n{folder}\n\n"
                "Pick the folder that contains a data/ subfolder "
                "(e.g. test_projects/project1).")
            return

        self.mod_folder = Path(folder).resolve()
        self.mod_root = info["mod_root"]
        self.mod_data_dir = info["data_dir"]
        self.install_root = info["install_root"]
        SDXml.atlas_search_dirs = info["atlas_search_dirs"]

        if info["sd_files"]:
            preference_order = ("strat3.sd.xml", "strat.sd.xml",
                                "stratpage.sd.xml")
            preferred = None
            for want in preference_order:
                for p in info["sd_files"]:
                    if p.name.lower() == want:
                        preferred = p
                        break
                if preferred:
                    break
            if preferred is None:
                preferred = info["sd_files"][0]
            self._load_sdxml_into_ui(preferred)

        lnt_tex_count = 0
        lnt_tga_count = 0
        if info["lnt_files"]:
            try:
                self.lnt_file = LntFile(info["lnt_files"][0])
                lnt_tex_count = len(self.lnt_file.textures)
                lnt_tga_count = len(self.lnt_file.tga_by_stem)
                self.lnt_search_var.set("")
                pages = ["(all)"] + (self.lnt_file.pages or [])
                self.lnt_page_combo["values"] = pages
                self.lnt_page_var.set(pages[1] if len(pages) > 1 else "(all)")
                self.draw_lnt()
            except Exception as e:
                messagebox.showerror("LNT load failed", str(e))

        self._update_lnt_info()

        self.file_label.config(
            text=f"Mod: {self.mod_root.name}  "
                 f"({len(info['sd_files'])} sd.xml, "
                 f"{len(info['lnt_files'])} lnt)")

        lines = [
            f"Mod root:   {self.mod_root}",
            f"Data dir:   {self.mod_data_dir}",
        ]
        if self.install_root is not None:
            lines.append(f"Install root: {self.install_root}")
        lines.append(f"Search dirs: {len(info['atlas_search_dirs'])}")
        lines.append("")
        lines.append(f"Found {len(info['sd_files'])} .sd.xml file(s).")
        lines.append(f"Found {len(info['lnt_files'])} .lnt file(s):")
        for p in info["lnt_files"][:12]:
            lines.append(f"  • {p.relative_to(self.mod_data_dir)}")
        lines.append("")
        if lnt_tex_count or lnt_tga_count:
            lines.append(f"LNT textures: {lnt_tex_count} region(s) from "
                         f"{lnt_tga_count} distinct .tga file(s).")

        self.status.config(
            text=f"Loaded mod '{self.mod_root.name}': "
                 f"{len(info['sd_files'])} sd.xml · "
                 f"{len(info['lnt_files'])} lnt · "
                 f"{lnt_tex_count} lnt regions · "
                 f"{lnt_tga_count} menu tgas")
        messagebox.showinfo("Mod folder loaded", "\n".join(lines))

    def _load_sdxml_into_ui(self, path):
        try:
            self.sdxml = SDXml(path)
        except Exception as e:
            messagebox.showerror("Load failed", f"{type(e).__name__}: {e}")
            return
        pages = list(self.sdxml.atlases.keys())
        self.atlas_combo["values"] = pages
        if pages:
            self.atlas_var.set(pages[0])
        names = [sp.name for sp in self.sdxml.sprites]
        self.mock_combo["values"] = names
        if names:
            self.mock_combo.set(names[0])
        self.refresh_sprite_list()
        self.refresh_atlas_view()

    # ------------------------------------------------------------------
    #  Tab 1: Sprites
    # ------------------------------------------------------------------
    def _build_sprites_tab(self):
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text="Sprites")

        bar = ttk.Frame(tab, padding=(4, 4))
        bar.pack(fill="x")
        ttk.Label(bar, text="Filter:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write",
                                  lambda *_: self.refresh_sprite_list())
        ttk.Entry(bar, textvariable=self.search_var,
                  width=30).pack(side="left", padx=4)
        ttk.Button(bar, text="Export selected as PNG…",
                   command=self.export_sprite_png).pack(side="left", padx=10)

        pane = ttk.PanedWindow(tab, orient="horizontal")
        pane.pack(fill="both", expand=True)

        left = ttk.Frame(pane)
        self.sprite_list = tk.Listbox(left, exportselection=False)
        self.sprite_list.pack(fill="both", expand=True, side="left")
        sb = ttk.Scrollbar(left, orient="vertical",
                           command=self.sprite_list.yview)
        sb.pack(side="right", fill="y")
        self.sprite_list.config(yscrollcommand=sb.set)
        self.sprite_list.bind("<<ListboxSelect>>", self.on_sprite_selected)
        pane.add(left, weight=2)

        right = ttk.Frame(pane, padding=8)
        self.preview_label = tk.Label(right, text="(no sprite selected)",
                                      background="#e8e8e8", anchor="center",
                                      width=40, height=15)
        self.preview_label.pack(fill="both", expand=True)
        self.sprite_info = ttk.Label(right, text="", justify="left",
                                     font=("TkFixedFont", 9))
        self.sprite_info.pack(fill="x", pady=8)

        edit = ttk.LabelFrame(right, text="Edit source coords (atlas position)",
                              padding=8)
        edit.pack(fill="x")
        self.edit_vars = {}
        for i, (label, key) in enumerate(
                [("Name", "name"), ("Page", "page"),
                 ("X", "x"), ("Y", "y"), ("W", "w"), ("H", "h")]):
            ttk.Label(edit, text=label, width=6).grid(row=i, column=0,
                                                      sticky="e", pady=2)
            v = tk.StringVar()
            ttk.Entry(edit, textvariable=v).grid(row=i, column=1,
                                                 sticky="ew", pady=2)
            self.edit_vars[key] = v
        edit.columnconfigure(1, weight=1)
        ttk.Button(edit, text="Apply",
                   command=self.apply_sprite_edits).grid(row=6, column=0,
                                                         columnspan=2,
                                                         pady=(6, 0),
                                                         sticky="ew")
        ttk.Label(right, text="Tip: x/y/w/h are coordinates inside the TGA,\n"
                              "not on-screen positions.",
                  foreground="#666", justify="left").pack(anchor="w",
                                                          pady=(8, 0))

        pane.add(right, weight=3)

    def refresh_sprite_list(self):
        self._filtered_indices = []
        self.sprite_list.delete(0, "end")
        if not self.sdxml:
            return
        needle = self.search_var.get().lower()
        for i, sp in enumerate(self.sdxml.sprites):
            if needle and needle not in sp.name.lower():
                continue
            self.sprite_list.insert("end", f"{sp.name}   ({sp.w}×{sp.h})")
            self._filtered_indices.append(i)

    def on_sprite_selected(self, event=None):
        sel = self.sprite_list.curselection()
        if not sel or not self._filtered_indices:
            return
        idx = self._filtered_indices[sel[0]]
        sp = self.sdxml.sprites[idx]
        self.current_sprite = sp

        if sp.crop is not None:
            crop = sp.crop
            cw, ch = crop.size
            max_side = 360
            if cw > max_side or ch > max_side:
                r = min(max_side / cw, max_side / ch)
                crop = crop.resize((max(1, int(cw * r)),
                                    max(1, int(ch * r))), RESAMPLE)
            try:
                self._preview_photo = ImageTk.PhotoImage(crop,
                                                         master=self.root)
                self.preview_label.config(image=self._preview_photo, text="")
            except Exception as e:
                self.preview_label.config(image="",
                                          text=f"(preview failed: {e})")
        else:
            self.preview_label.config(image="", text="(no atlas image)")

        self.sprite_info.config(
            text=f"Name: {sp.name}\n"
                 f"Atlas page: {sp.page}\n"
                 f"Size: {sp.w} × {sp.h}\n"
                 f"Atlas coords: ({sp.x}, {sp.y})")

        self.edit_vars["name"].set(sp.name)
        self.edit_vars["page"].set(sp.page)
        self.edit_vars["x"].set(str(sp.x))
        self.edit_vars["y"].set(str(sp.y))
        self.edit_vars["w"].set(str(sp.w))
        self.edit_vars["h"].set(str(sp.h))

    def apply_sprite_edits(self):
        if not self.current_sprite:
            return
        sp = self.current_sprite
        try:
            sp.name = self.edit_vars["name"].get() or sp.name
            sp.x = int(self.edit_vars["x"].get())
            sp.y = int(self.edit_vars["y"].get())
            sp.w = max(1, int(self.edit_vars["w"].get()))
            sp.h = max(1, int(self.edit_vars["h"].get()))
            self.sdxml.refresh_crop(sp)
        except ValueError:
            messagebox.showerror("Invalid", "X, Y, W, H must be integers.")
            return
        self.refresh_sprite_list()
        self.on_sprite_selected()
        self.refresh_atlas_view()

    def export_sprite_png(self):
        if not self.current_sprite or self.current_sprite.crop is None:
            messagebox.showinfo("No sprite",
                                "Select a sprite with image data first.")
            return
        p = filedialog.asksaveasfilename(
            defaultextension=".png", filetypes=[("PNG", "*.png")],
            initialfile=f"{self.current_sprite.name}.png")
        if p:
            self.current_sprite.crop.save(p)
            self.status.config(text=f"Exported {p}")

    # ------------------------------------------------------------------
    #  Tab 2: Atlases
    # ------------------------------------------------------------------
    def _build_atlas_tab(self):
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text="Atlases")

        bar = ttk.Frame(tab, padding=(4, 4))
        bar.pack(fill="x")
        ttk.Label(bar, text="Atlas page:").pack(side="left")
        self.atlas_var = tk.StringVar()
        self.atlas_combo = ttk.Combobox(bar, textvariable=self.atlas_var,
                                        state="readonly", width=40)
        self.atlas_combo.pack(side="left", padx=4)
        self.atlas_combo.bind("<<ComboboxSelected>>",
                              lambda e: self.refresh_atlas_view())
        ttk.Button(bar, text="Export this atlas as TGA…",
                   command=self.export_current_atlas).pack(side="left", padx=10)
        ttk.Label(bar,
                  text="Green = sprite.  Click and drag a box to repack it.",
                  foreground="#666").pack(side="left", padx=8)

        self.atlas_canvas = tk.Canvas(tab, bg="#2a2f36", highlightthickness=0)
        self.atlas_canvas.pack(fill="both", expand=True)

        self.atlas_canvas.bind("<ButtonPress-1>", self._atlas_down)
        self.atlas_canvas.bind("<B1-Motion>", self._atlas_move)
        self.atlas_canvas.bind("<ButtonRelease-1>",
                               lambda e: setattr(self, "_atlas_drag", None))
        self.atlas_canvas.bind("<Configure>",
                               lambda e: self.refresh_atlas_view())

    def refresh_atlas_view(self):
        if not hasattr(self, "atlas_canvas"):
            return
        c = self.atlas_canvas
        c.delete("all")
        self._atlas_rects = {}
        if not self.sdxml:
            return
        page = self.atlas_var.get()
        if not page or page not in self.sdxml.atlases:
            c.create_text(20, 20, anchor="nw", fill="#aaa",
                          text="Open a .sd.xml to see its atlases.")
            return
        atlas = self.sdxml.atlases[page]
        if atlas is None:
            c.create_text(20, 20, anchor="nw", fill="#e88",
                          text=f"Atlas file not found: {page}")
            return

        cw = max(c.winfo_width(), 100)
        ch = max(c.winfo_height(), 100)
        aw, ah = atlas.size
        s = min((cw - 20) / aw, (ch - 20) / ah, 1.0)
        self._atlas_scale = s
        self._atlas_origin = (int((cw - aw * s) / 2),
                              int((ch - ah * s) / 2))

        scaled = atlas.resize((max(1, int(aw * s)), max(1, int(ah * s))),
                              RESAMPLE)
        try:
            self._atlas_photo = ImageTk.PhotoImage(scaled, master=self.root)
        except Exception as e:
            c.create_text(20, 20, anchor="nw", fill="#e88",
                          text=f"Could not create preview image: {e}")
            return
        c.create_image(self._atlas_origin[0], self._atlas_origin[1],
                       image=self._atlas_photo, anchor="nw")

        for sp in self.sdxml.sprites:
            if sp.page != page:
                continue
            x1 = self._atlas_origin[0] + sp.x * s
            y1 = self._atlas_origin[1] + sp.y * s
            x2 = x1 + sp.w * s
            y2 = y1 + sp.h * s
            color = "#ffcc44" if sp is self._atlas_selected else "#44cc88"
            rect = c.create_rectangle(x1, y1, x2, y2, outline=color,
                                      width=2, tags=("sprite", sp.name))
            self._atlas_rects[rect] = sp
            if s > 0.4:
                c.create_text(x1 + 2, y1 + 2, text=sp.name, anchor="nw",
                              fill="#fff", font=("TkDefaultFont", 7))

    def _atlas_down(self, event):
        if not self.sdxml:
            return
        found = None
        for rect, sp in reversed(list(self._atlas_rects.items())):
            bbox = self.atlas_canvas.coords(rect)
            if len(bbox) == 4 and bbox[0] <= event.x <= bbox[2] \
                    and bbox[1] <= event.y <= bbox[3]:
                found = sp
                break
        if found is None:
            self._atlas_drag = None
            return
        self._atlas_selected = found
        self._atlas_drag = {
            "sprite": found,
            "start": (event.x, event.y),
            "orig": (found.x, found.y),
        }
        self.refresh_atlas_view()
        self._select_sprite_in_list(found)

    def _atlas_move(self, event):
        if not self._atlas_drag:
            return
        sp = self._atlas_drag["sprite"]
        x0, y0 = self._atlas_drag["start"]
        ox, oy = self._atlas_drag["orig"]
        s = self._atlas_scale or 1
        sp.x = max(0, int(round(ox + (event.x - x0) / s)))
        sp.y = max(0, int(round(oy + (event.y - y0) / s)))
        self.sdxml.refresh_crop(sp)
        self.refresh_atlas_view()
        if self.current_sprite is sp:
            self.edit_vars["x"].set(str(sp.x))
            self.edit_vars["y"].set(str(sp.y))

    def _select_sprite_in_list(self, sprite):
        if sprite not in self.sdxml.sprites:
            return
        idx_in_all = self.sdxml.sprites.index(sprite)
        if idx_in_all in self._filtered_indices:
            pos = self._filtered_indices.index(idx_in_all)
            self.sprite_list.selection_clear(0, "end")
            self.sprite_list.selection_set(pos)
            self.sprite_list.see(pos)

    def export_current_atlas(self):
        page = self.atlas_var.get()
        if not page or not self.sdxml or page not in self.sdxml.atlases:
            return
        atlas = self.sdxml.atlases[page]
        if atlas is None:
            return
        p = filedialog.asksaveasfilename(
            defaultextension=".tga",
            initialfile=Path(page).name,
            filetypes=[("TGA", "*.tga"), ("PNG", "*.png")])
        if not p:
            return
        try:
            if p.lower().endswith(".tga"):
                atlas.save(p, format="TGA")
            else:
                atlas.save(p)
            self.status.config(text=f"Atlas exported to {p}")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))

    # ------------------------------------------------------------------
    #  Tab 3: HUD Mockup
    # ------------------------------------------------------------------
    def _build_mockup_tab(self):
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text="HUD Mockup")

        bar = ttk.Frame(tab, padding=(4, 4))
        bar.pack(fill="x")
        ttk.Label(bar, text="Add sprite:").pack(side="left")
        self.mock_combo = ttk.Combobox(bar, state="readonly", width=36)
        self.mock_combo.pack(side="left", padx=4)
        ttk.Button(bar, text="Add to canvas",
                   command=self.add_to_mock).pack(side="left", padx=2)
        ttk.Button(bar, text="Vanilla HUD reference",
                   command=self.load_vanilla_hud_reference).pack(side="left",
                                                                 padx=6)
        ttk.Button(bar, text="Refresh images",
                   command=self.refresh_mock_images).pack(side="left", padx=4)
        ttk.Button(bar, text="Clear",
                   command=self.clear_mock).pack(side="left", padx=8)
        ttk.Button(bar, text="Save PNG…",
                   command=self.save_mock_png).pack(side="left", padx=4)
        ttk.Button(bar, text="Save layout JSON…",
                   command=self.save_mock_json).pack(side="left", padx=4)
        ttk.Button(bar, text="Load layout…",
                   command=self.load_mock_json).pack(side="left", padx=4)
        ttk.Label(bar,
                  text="Reference only — does not affect the in-game HUD.",
                  foreground="#666").pack(side="left", padx=12)

        pane = ttk.PanedWindow(tab, orient="horizontal")
        pane.pack(fill="both", expand=True)

        self.mock_canvas = tk.Canvas(pane, bg="#22262b", highlightthickness=0)
        pane.add(self.mock_canvas, weight=4)

        side = ttk.Frame(pane, padding=6)
        pane.add(side, weight=1)

        ttk.Label(side, text="Mockup items",
                  font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        self.mock_list = tk.Listbox(side, exportselection=False, height=18)
        self.mock_list.pack(fill="both", expand=True)
        self.mock_list.bind("<<ListboxSelect>>", self.on_mock_list_select)
        ttk.Button(side, text="Remove selected",
                   command=self.remove_mock).pack(fill="x", pady=4)

        pf = ttk.LabelFrame(side, text="Selected item", padding=6)
        pf.pack(fill="x", pady=6)
        self.mock_vars = {}
        for i, (label, key) in enumerate(
                [("Name", "name"), ("X", "x"), ("Y", "y"),
                 ("Width", "w"), ("Height", "h")]):
            ttk.Label(pf, text=label, width=6).grid(row=i, column=0,
                                                    sticky="e")
            v = tk.StringVar()
            ttk.Entry(pf, textvariable=v, width=10).grid(row=i, column=1,
                                                         sticky="ew", pady=2)
            self.mock_vars[key] = v
        pf.columnconfigure(1, weight=1)
        ttk.Button(pf, text="Apply", command=self.apply_mock_props).grid(
            row=5, column=0, columnspan=2, pady=(6, 0), sticky="ew")

        self.mock_canvas.bind("<ButtonPress-1>", self._mock_down)
        self.mock_canvas.bind("<B1-Motion>", self._mock_move)
        self.mock_canvas.bind("<ButtonRelease-1>",
                              lambda e: setattr(self, "mock_drag", None))
        self.mock_canvas.bind("<Configure>", lambda e: self.draw_mock())

    def load_vanilla_hud_reference(self):
        if not self.sdxml:
            messagebox.showinfo(
                "No sprites loaded",
                "Open a strat3.sd.xml first so the HUD panels can be placed.")
            return
        by_name = {sp.name: sp for sp in self.sdxml.sprites}
        added, missing = 0, []
        for name, x, y, w, h in VANILLA_HUD:
            sp = by_name.get(name)
            if sp is None:
                missing.append(name)
                continue
            self.mock_items.append({
                "name": name, "x": x, "y": y, "w": w, "h": h,
                "image": sp.crop,
            })
            added += 1
        self.refresh_mock_list()
        if self.mock_items:
            self.mock_selected = self.mock_items[-1]
            self.update_mock_props()
        self.draw_mock()
        if added:
            msg = f"Placed {added} vanilla HUD panel(s)."
            if missing:
                msg += f"  Missing: {', '.join(missing)}"
            self.status.config(text=msg)
        else:
            messagebox.showinfo(
                "Not found",
                "None of STRAT_HUD_LEFT / MIDDLE / RIGHT were in the "
                "loaded .sd.xml.")

    def add_to_mock(self):
        if not self.sdxml:
            return
        sel = self.sprite_list.curselection()
        if not sel or not self._filtered_indices:
            messagebox.showinfo("No sprite",
                                "Select a sprite in the Sprites tab first.")
            return
        sp = self.sdxml.sprites[self._filtered_indices[sel[0]]]
        item = {"name": sp.name, "x": 40, "y": 40,
                "w": sp.w, "h": sp.h, "image": sp.crop}
        self.mock_items.append(item)
        self.refresh_mock_list()
        self.mock_selected = item
        self.update_mock_props()
        self.draw_mock()

    def clear_mock(self):
        if self.mock_items and not messagebox.askyesno(
                "Clear canvas", "Remove all items from the mockup?"):
            return
        self.mock_items = []
        self.mock_selected = None
        self.refresh_mock_list()
        self.update_mock_props()
        self.draw_mock()

    def remove_mock(self):
        if self.mock_selected in self.mock_items:
            self.mock_items.remove(self.mock_selected)
            self.mock_selected = None
            self.refresh_mock_list()
            self.update_mock_props()
            self.draw_mock()

    def refresh_mock_images(self):
        if not self.mock_items:
            self.status.config(text="No mockup items to refresh.")
            return
        recovered = 0
        for it in self.mock_items:
            before = it.get("image")
            it["image"] = None
            self._mock_image(it)
            if it.get("image") is not None and before is None:
                recovered += 1
        self.draw_mock()
        self.status.config(
            text=f"Refreshed {len(self.mock_items)} mockup item(s); "
                 f"{recovered} image(s) recovered.")

    def refresh_mock_list(self):
        self.mock_list.delete(0, "end")
        for it in self.mock_items:
            self.mock_list.insert("end",
                                  f"{it['name']}  ({it['w']}×{it['h']})")

    def on_mock_list_select(self, event=None):
        s = self.mock_list.curselection()
        if not s:
            return
        self.mock_selected = self.mock_items[s[0]]
        self.update_mock_props()
        self.draw_mock()

    def update_mock_props(self):
        it = self.mock_selected
        if it is None:
            for v in self.mock_vars.values():
                v.set("")
            return
        for k, v in self.mock_vars.items():
            v.set(str(it.get(k, "")))

    def apply_mock_props(self):
        it = self.mock_selected
        if it is None:
            return
        try:
            it["name"] = self.mock_vars["name"].get() or it["name"]
            it["x"] = int(self.mock_vars["x"].get())
            it["y"] = int(self.mock_vars["y"].get())
            it["w"] = max(1, int(self.mock_vars["w"].get()))
            it["h"] = max(1, int(self.mock_vars["h"].get()))
        except ValueError:
            self.update_mock_props()
            return
        self.refresh_mock_list()
        self.draw_mock()

    def _mock_image(self, it):
        img = it.get("image")
        if img is not None:
            return img
        if self.sdxml:
            for sp in self.sdxml.sprites:
                if sp.name == it.get("name"):
                    if sp.crop is None:
                        self.sdxml.refresh_crop(sp)
                    if sp.crop is not None:
                        it["image"] = sp.crop
                        return sp.crop
        return None

    def draw_mock(self):
        if not hasattr(self, "mock_canvas"):
            return
        c = self.mock_canvas
        c.delete("all")
        cw = max(c.winfo_width(), 100)
        ch = max(c.winfo_height(), 100)
        s = min((cw - 40) / HUD_W, (ch - 40) / HUD_H)
        self.mock_scale = s
        ox = int((cw - HUD_W * s) / 2)
        oy = int((ch - HUD_H * s) / 2)
        self.mock_origin = (ox, oy)

        c.create_rectangle(ox, oy, ox + HUD_W * s, oy + HUD_H * s,
                           fill="#3a4148", outline="#7a828a")
        c.create_text(ox + 6, oy + 4, anchor="nw", fill="#cfd8e0",
                      font=("TkDefaultFont", 8),
                      text=f"HUD preview · {HUD_W}×{HUD_H}")

        self.mock_photos = []
        missing = 0
        for it in self.mock_items:
            x = ox + it["x"] * s
            y = oy + it["y"] * s
            w = max(1, int(it["w"] * s))
            h = max(1, int(it["h"] * s))
            img = self._mock_image(it)
            drawn = False
            if img is not None:
                try:
                    scaled = img.resize((w, h), RESAMPLE)
                    ph = ImageTk.PhotoImage(scaled, master=self.root)
                    self.mock_photos.append(ph)
                    c.create_image(x, y, image=ph, anchor="nw",
                                   tags=("mock", str(id(it))))
                    drawn = True
                except Exception:
                    pass
            if not drawn:
                missing += 1
                c.create_rectangle(x, y, x + w, y + h,
                                   fill="#556", outline="#889",
                                   tags=("mock", str(id(it))))
            if it is self.mock_selected:
                c.create_rectangle(x, y, x + w, y + h,
                                   outline="#ffcc44", width=2,
                                   tags=("mock", str(id(it))))

        if missing and self.mock_items:
            c.create_text(ox + 6, oy + HUD_H * s - 18, anchor="sw",
                          fill="#ffcc44", font=("TkDefaultFont", 8),
                          text=f"{missing} item(s) have no image — "
                               f"click Refresh images")

    def _mock_down(self, event):
        ids = self.mock_canvas.find_overlapping(event.x, event.y,
                                                event.x, event.y)
        for i in reversed(ids):
            for t in self.mock_canvas.gettags(i):
                if t.isdigit():
                    item = next((x for x in self.mock_items
                                 if id(x) == int(t)), None)
                    if item is not None:
                        self.mock_selected = item
                        self.update_mock_props()
                        self.refresh_mock_list()
                        self.mock_drag = {
                            "item": item,
                            "start": (event.x, event.y),
                            "orig": (item["x"], item["y"]),
                        }
                        self.draw_mock()
                        return
        self.mock_selected = None
        self.update_mock_props()
        self.draw_mock()

    def _mock_move(self, event):
        if not self.mock_drag:
            return
        it = self.mock_drag["item"]
        x0, y0 = self.mock_drag["start"]
        ox, oy = self.mock_drag["orig"]
        s = self.mock_scale or 1
        it["x"] = max(0, int(ox + (event.x - x0) / s))
        it["y"] = max(0, int(oy + (event.y - y0) / s))
        self.update_mock_props()
        self.draw_mock()

    def save_mock_png(self):
        if not self.mock_items or not HAS_PIL:
            return
        p = filedialog.asksaveasfilename(
            defaultextension=".png", filetypes=[("PNG", "*.png")])
        if not p:
            return
        try:
            img = Image.new("RGBA", (HUD_W, HUD_H), (0, 0, 0, 0))
            for it in self.mock_items:
                src = self._mock_image(it)
                if src is None:
                    continue
                scaled = src.resize((max(1, it["w"]), max(1, it["h"])),
                                    RESAMPLE)
                img.alpha_composite(scaled, (it["x"], it["y"]))
            img.save(p)
            self.status.config(text=f"Mockup exported to {p}")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))

    def save_mock_json(self):
        if not self.mock_items:
            return
        p = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not p:
            return
        data = [{"name": it["name"], "x": it["x"], "y": it["y"],
                 "w": it["w"], "h": it["h"]} for it in self.mock_items]
        Path(p).write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.status.config(text=f"Layout saved to {p}")

    def load_mock_json(self):
        p = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not p:
            return
        try:
            data = json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception as e:
            messagebox.showerror("Load failed", str(e))
            return
        by_name = {sp.name: sp for sp in (self.sdxml.sprites
                                          if self.sdxml else [])}
        self.mock_items = []
        for d in data:
            sp = by_name.get(d.get("name", ""))
            self.mock_items.append({
                "name": d.get("name", ""),
                "x": int(d.get("x", 0)), "y": int(d.get("y", 0)),
                "w": int(d.get("w", 10)), "h": int(d.get("h", 10)),
                "image": sp.crop if sp else None,
            })
        self.refresh_mock_list()
        self.draw_mock()

    # ------------------------------------------------------------------
    #  Tab 4: Menu (LNT)
    # ------------------------------------------------------------------
    def _build_lnt_tab(self):
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text="Menu (LNT)")

        bar = ttk.Frame(tab, padding=(4, 4))
        bar.pack(fill="x")
        ttk.Button(bar, text="Open .lnt…",
                   command=self.open_lnt).pack(side="left", padx=2)
        ttk.Button(bar, text="Save .lnt (backup first)",
                   command=self.save_lnt).pack(side="left", padx=2)
        ttk.Button(bar, text="Reload",
                   command=self.reload_lnt).pack(side="left", padx=2)
        ttk.Button(bar, text="Reload textures",
                   command=self.reload_lnt_textures).pack(side="left", padx=2)

        ttk.Label(bar, text="Search:").pack(side="left", padx=(12, 2))
        self.lnt_search_var = tk.StringVar()
        self.lnt_search_var.trace_add(
            "write", lambda *_: self._refresh_lnt_page_list())
        ttk.Entry(bar, textvariable=self.lnt_search_var,
                  width=14).pack(side="left", padx=2)

        ttk.Label(bar, text="Page:").pack(side="left", padx=(8, 2))
        self.lnt_page_var = tk.StringVar()
        self.lnt_page_combo = ttk.Combobox(bar,
                                           textvariable=self.lnt_page_var,
                                           state="readonly", width=28)
        self.lnt_page_combo.pack(side="left")
        self.lnt_page_combo.bind("<<ComboboxSelected>>",
                                 lambda e: self.draw_lnt())
        self.lnt_page_var.trace_add("write",
                                    lambda *_: self.root.after_idle(
                                        self.draw_lnt))

        self.lnt_info = ttk.Label(tab, text="No .lnt loaded — "
                                            "click 'Pick mod folder…'",
                                  padding=(6, 2), foreground="#666")
        self.lnt_info.pack(fill="x")

        self.lnt_canvas = tk.Canvas(tab, bg="#22262b", highlightthickness=0)
        self.lnt_canvas.pack(fill="both", expand=True)
        self.lnt_canvas.bind("<ButtonPress-1>", self._lnt_down)
        self.lnt_canvas.bind("<B1-Motion>", self._lnt_move)
        self.lnt_canvas.bind("<ButtonRelease-1>",
                             lambda e: setattr(self, "lnt_drag", None))
        self.lnt_canvas.bind("<Configure>", lambda e: self.draw_lnt())

    def _refresh_lnt_page_list(self):
        if not self.lnt_file:
            return
        needle = self.lnt_search_var.get().lower()
        all_pages = ["(all)"] + (self.lnt_file.pages or [])
        if needle:
            pages = [p for p in all_pages if needle in p.lower()]
        else:
            pages = all_pages
        self.lnt_page_combo["values"] = pages
        current = self.lnt_page_combo.get()
        if current not in pages:
            new = pages[0] if pages else ""
            self.lnt_page_combo.set(new)
            self.draw_lnt()

    def open_lnt(self):
        p = filedialog.askopenfilename(
            title="Open menu layout (.lnt)",
            initialdir=str(self.mod_data_dir
                           or self.mod_folder
                           or Path(__file__).resolve().parent),
            filetypes=[("LNT menu files", "*.lnt"),
                       ("All files", "*.*")])
        if not p:
            return
        try:
            self.lnt_file = LntFile(p)
        except Exception as e:
            messagebox.showerror("LNT load failed", str(e))
            return
        self.lnt_search_var.set("")
        pages = ["(all)"] + (self.lnt_file.pages or [])
        self.lnt_page_combo["values"] = pages
        self.lnt_page_var.set(pages[1] if len(pages) > 1 else "(all)")
        self._update_lnt_info()
        self.status.config(
            text=f"Loaded {len(self.lnt_file.pieces)} UI pieces · "
                 f"{len(self.lnt_file.textures)} texture region(s) from "
                 f"{len(self.lnt_file.tga_by_stem)} tga(s) · "
                 f"{Path(p).name}")
        self.draw_lnt()

    def reload_lnt(self):
        if self.lnt_file:
            self.open_lnt_path(self.lnt_file.path)

    def reload_lnt_textures(self):
        if not self.lnt_file:
            return
        self.lnt_file.textures = {}
        self.lnt_file.tga_by_stem = {}
        self.lnt_file._load_textures()
        self._update_lnt_info()
        self.draw_lnt()
        self.status.config(
            text=f"Reloaded LNT textures: {len(self.lnt_file.textures)} "
                 f"region(s) from {len(self.lnt_file.tga_by_stem)} tga(s).")

    def open_lnt_path(self, path):
        try:
            self.lnt_file = LntFile(path)
        except Exception as e:
            messagebox.showerror("LNT reload failed", str(e))
            return
        self.lnt_search_var.set("")
        pages = ["(all)"] + (self.lnt_file.pages or [])
        self.lnt_page_combo["values"] = pages
        self.lnt_page_var.set(pages[1] if len(pages) > 1 else "(all)")
        self._update_lnt_info()
        self.draw_lnt()

    def save_lnt(self):
        if not self.lnt_file:
            return
        if not messagebox.askyesno(
                "Save .lnt",
                f"Write changes back to:\n{self.lnt_file.path}\n\n"
                "A .bak copy will be created."):
            return
        try:
            bak = self.lnt_file.path.with_suffix(
                self.lnt_file.path.suffix + ".bak")
            if not bak.exists():
                shutil.copy2(self.lnt_file.path, bak)
            self.lnt_file.save()
            self.status.config(text=f"Saved {self.lnt_file.path.name}")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    def _update_lnt_info(self):
        if not hasattr(self, "lnt_info"):
            return
        if not self.lnt_file:
            self.lnt_info.config(
                text="No .lnt loaded — click 'Pick mod folder…'",
                foreground="#886")
            return
        regions = len(self.lnt_file.textures)
        tgas = len(self.lnt_file.tga_by_stem)
        pieces = len(self.lnt_file.pieces)
        pages = len(self.lnt_file.pages)
        colour = "#484" if regions else "#886"
        self.lnt_info.config(
            text=f"{pieces} piece(s) · {pages} page(s) · "
                 f"{regions} texture region(s) from {tgas} tga file(s)",
            foreground=colour)

    # ------------------------------------------------------------------
    #  Text style helpers for menu pieces
    # ------------------------------------------------------------------
    def _display_text_for_piece(self, pc):
        """Return a nice menu-style display string for a piece, or empty
        string if we can't produce anything meaningful.

        Preference order:
          1. <UI text> value if present (with UI_ prefix stripped)
          2. The piece name with context stripped and words capitalised
        """
        raw = (pc.get("text") or "").strip()
        if raw:
            for pfx in ("UI_", "ui_"):
                if raw.startswith(pfx):
                    raw = raw[len(pfx):]
                    break
            label = self._pretty_label(raw)
            if label:
                return label
        return self._pretty_label(pc.get("name", ""))

    # Words that provide menu context but aren't interesting as a label
    # on their own.  We drop these from the START of the identifier only.
    _CONTEXT_WORDS = {
        "main", "menu", "new", "game", "options", "impcam",
        "historical", "battle", "pc", "res", "text", "button",
        "ui", "info", "title",
    }

    # Compound word fixes for common identifiers that we know about.
    _COMPOUND_FIXES = (
        ("Singleplayer", "Single Player"),
        ("Multiplayer", "Multiplayer"),
        ("Autoresolve", "Auto Resolve"),
        ("Loadgame", "Load Game"),
        ("Savegame", "Save Game"),
        ("Quickbattle", "Quick Battle"),
        ("Custombattle", "Custom Battle"),
        ("Provincialcampaign", "Provincial Campaign"),
        ("Imperialcampaign", "Imperial Campaign"),
        ("Historicalbattles", "Historical Battles"),
    )

    def _pretty_label(self, raw):
        """Turn 'main_menu_singleplayer' into 'Single Player' etc."""
        if not raw:
            return ""
        s = raw.replace("_", " ").strip()
        # Insert a space between camelCase word boundaries
        s = _re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)
        words = s.split()
        # Drop leading context words, but only if there is something left
        while len(words) > 1 and words[0].lower() in self._CONTEXT_WORDS:
            words.pop(0)
        if not words:
            return ""
        label = " ".join(w.capitalize() for w in words)
        # Apply compound-word fixes
        for before, after in self._COMPOUND_FIXES:
            if label == before:
                return after
        return label

    # ------------------------------------------------------------------
    def draw_lnt(self):
        if not hasattr(self, "lnt_canvas"):
            return
        c = self.lnt_canvas
        c.delete("all")
        self._lnt_photos = []

        if not self.lnt_file:
            c.create_text(20, 20, anchor="nw", fill="#aaa",
                          text="Pick a mod folder, or use 'Open .lnt…' to "
                               "load a file directly.")
            return

        current = self.lnt_page_combo.get() or "(all)"

        visible = []
        for pc in self.lnt_file.pieces:
            if current and current != "(all)" and pc.get("page") \
                    and pc["page"] != current:
                continue
            visible.append(pc)

        if visible:
            minx = min(pc["x"] for pc in visible)
            miny = min(pc["y"] for pc in visible)
            maxx = max(pc["x"] + pc["w"] for pc in visible)
            maxy = max(pc["y"] + pc["h"] for pc in visible)
            minx = max(0, minx - 20)
            miny = max(0, miny - 20)
            maxx = min(self.lnt_file.width,  maxx + 20)
            maxy = min(self.lnt_file.height, maxy + 20)
            bw = max(1, maxx - minx)
            bh = max(1, maxy - miny)
        else:
            minx, miny = 0, 0
            bw, bh = self.lnt_file.width, self.lnt_file.height

        cw = max(c.winfo_width(), 200)
        ch = max(c.winfo_height(), 200)
        s = min((cw - 40) / bw, (ch - 40) / bh)
        s = min(s, 4.0)
        self._lnt_scale = s
        ox = int((cw - bw * s) / 2) - int(minx * s)
        oy = int((ch - bh * s) / 2) - int(miny * s)
        self._lnt_origin = (ox, oy)

        regions_ci = {k.lower(): v
                      for k, v in (self.lnt_file.textures or {}).items()}
        stems_ci = {k.lower(): v
                    for k, v in (self.lnt_file.tga_by_stem or {}).items()}

        matched = 0
        for pc in visible:
            x = ox + pc["x"] * s
            y = oy + pc["y"] * s
            w = max(1, int(pc["w"] * s))
            h = max(1, int(pc["h"] * s))
            tag = str(id(pc))

            img = None
            for key in (pc.get("name"), pc.get("identifier"),
                        pc.get("object_id")):
                if not key:
                    continue
                lower = key.lower()
                if lower in regions_ci:
                    img = regions_ci[lower]
                    break
                if lower in stems_ci:
                    img = stems_ci[lower]
                    break

            drew_sprite = False
            if img is not None:
                try:
                    scaled = img.resize((w, h), RESAMPLE)
                    ph = ImageTk.PhotoImage(scaled, master=self.root)
                    self._lnt_photos.append(ph)
                    c.create_image(x, y, image=ph, anchor="nw",
                                   tags=("lnt", tag))
                    drew_sprite = True
                    matched += 1
                except Exception:
                    drew_sprite = False

            is_selected = (pc is self.lnt_selected)
            if is_selected:
                c.create_rectangle(x, y, x + w, y + h,
                                   outline="#ffcc44", width=2,
                                   tags=("lnt", tag))
            elif not drew_sprite:
                c.create_rectangle(x, y, x + w, y + h,
                                   outline="#44cc88", width=1,
                                   tags=("lnt", tag))

            # ---------- text rendering ----------
            if not drew_sprite:
                # No artwork — draw menu-style centered serif text.
                label = self._display_text_for_piece(pc)
                if label:
                    # Scale font to piece height, with sane limits.
                    fs = max(7, min(22, int(h * 0.42)))
                    cx = x + w / 2
                    cy = y + h / 2
                    # Faint drop-shadow gives the gold text a bit of
                    # depth, similar to the game's engraved look.
                    c.create_text(cx + 1, cy + 1, text=label,
                                  anchor="center",
                                  fill=MENU_TEXT_SHADOW,
                                  font=(self.ui_serif, fs, "bold"),
                                  tags=("lnt", tag))
                    c.create_text(cx, cy, text=label,
                                  anchor="center",
                                  fill=MENU_TEXT_COLOR,
                                  font=(self.ui_serif, fs, "bold"),
                                  tags=("lnt", tag))
                else:
                    # Nothing useful to display — show the raw name in
                    # a small neutral font so the piece is still
                    # identifiable during editing.
                    c.create_text(x + w / 2, y + h / 2,
                                  text=pc["name"], anchor="center",
                                  fill="#889", font=("TkDefaultFont", 8),
                                  tags=("lnt", tag))
            elif w > 60:
                # Piece has artwork — keep a small utility label so the
                # piece name is still discoverable during editing.
                c.create_text(x + 2, y + 1, anchor="nw", fill="#7a8288",
                              font=("TkDefaultFont", 6), text=pc["name"],
                              tags=("lnt", tag))

        c.create_text(8, 8, anchor="nw", fill="#cfd8e0",
                      font=("TkDefaultFont", 8),
                      text=f"Page: {current} · {len(visible)} piece(s) · "
                           f"{matched} matched · zoom {s:.2f}×")

    def _lnt_down(self, event):
        if not self.lnt_file:
            return
        current = self.lnt_page_combo.get() or "(all)"
        ids = self.lnt_canvas.find_overlapping(event.x, event.y,
                                               event.x, event.y)
        for i in reversed(ids):
            for t in self.lnt_canvas.gettags(i):
                if t.isdigit():
                    pc = next((x for x in self.lnt_file.pieces
                               if id(x) == int(t)), None)
                    if pc is None:
                        continue
                    if current and current != "(all)" \
                            and pc.get("page") and pc["page"] != current:
                        continue
                    self.lnt_selected = pc
                    self.lnt_drag = {
                        "piece": pc,
                        "start": (event.x, event.y),
                        "orig": (pc["x"], pc["y"]),
                    }
                    self.draw_lnt()
                    return

    def _lnt_move(self, event):
        if not self.lnt_drag:
            return
        pc = self.lnt_drag["piece"]
        x0, y0 = self.lnt_drag["start"]
        ox, oy = self.lnt_drag["orig"]
        s = getattr(self, "_lnt_scale", 1.0) or 1.0
        nx = max(0, int(round(ox + (event.x - x0) / s)))
        ny = max(0, int(round(oy + (event.y - y0) / s)))
        self.lnt_file.update_piece(pc, x=nx, y=ny)
        self.draw_lnt()

    # ------------------------------------------------------------------
    #  File ops
    # ------------------------------------------------------------------
    def open_sd(self):
        if not HAS_PIL:
            messagebox.showerror("Pillow required",
                                 "Install Pillow:\n    pip install pillow")
            return
        p = filedialog.askopenfilename(
            title="Open .sd.xml sprite definition",
            initialdir=str(self.mod_data_dir
                           or self.mod_folder
                           or Path(__file__).resolve().parent),
            filetypes=[("Sprite definition", "*.sd.xml"),
                       ("XML", "*.xml"), ("All files", "*.*")])
        if not p:
            return
        self._load_sdxml_into_ui(Path(p))
        self._update_lnt_info()
        found = sum(1 for a in self.sdxml.atlases.values() if a is not None)
        self.status.config(
            text=f"{len(self.sdxml.sprites)} sprites · "
                 f"{len(self.sdxml.atlases)} atlas page(s) · "
                 f"{found} atlas image(s) loaded.")

    def set_atlas_folder(self):
        d = filedialog.askdirectory(
            title="Folder containing TGA files")
        if not d:
            return
        if Path(d) not in SDXml.atlas_search_dirs:
            SDXml.atlas_search_dirs.insert(0, Path(d))
        self.status.config(text=f"Added search folder: {d}")
        if self.sdxml:
            self._reload_sdxml()
        if self.lnt_file:
            self.reload_lnt_textures()

    def _reload_sdxml(self):
        if not self.sdxml:
            return
        p = self.sdxml.path
        try:
            self.sdxml = SDXml(p)
        except Exception as e:
            messagebox.showerror("Reload failed", str(e))
            return
        pages = list(self.sdxml.atlases.keys())
        self.atlas_combo["values"] = pages
        if pages:
            self.atlas_var.set(pages[0])
        self.mock_combo["values"] = [sp.name for sp in self.sdxml.sprites]
        self.refresh_sprite_list()
        self.refresh_atlas_view()
        self._update_lnt_info()
        found = sum(1 for a in self.sdxml.atlases.values() if a is not None)
        self.status.config(
            text=f"Reloaded {p.name} · {len(self.sdxml.sprites)} sprites · "
                 f"{found} of {len(pages)} atlases found")

    def show_file_info(self):
        if not self.sdxml and not self.mod_root and not self.lnt_file:
            messagebox.showinfo("No file",
                                "Pick a mod folder, or open a file first.")
            return
        lines = []
        if self.mod_root is not None:
            lines.append(f"Mod root:   {self.mod_root}")
            lines.append(f"Data dir:   {self.mod_data_dir}")
            if self.install_root is not None:
                lines.append(f"Install:    {self.install_root}")
            lines.append(
                f"Search dirs: {len(SDXml.atlas_search_dirs)}")
            for d in SDXml.atlas_search_dirs[:12]:
                lines.append(f"  • {d}")
            if len(SDXml.atlas_search_dirs) > 12:
                lines.append(
                    f"  … and {len(SDXml.atlas_search_dirs) - 12} more")
            lines.append("")
        if self.sdxml is not None:
            lines.append(f"Loaded .sd.xml: {self.sdxml.path}")
            lines.append("Atlas pages:")
            for fname, img in self.sdxml.atlases.items():
                if img is None:
                    lines.append(f"  ✗ {fname}  — NOT FOUND")
                else:
                    lines.append(
                        f"  ✓ {fname}  — {img.width}×{img.height}")
            lines.append("")
        if self.lnt_file is not None:
            lines.append(f"Loaded .lnt: {self.lnt_file.path}")
            lines.append(
                f"  {len(self.lnt_file.pieces)} piece(s) across "
                f"{len(self.lnt_file.pages)} page(s)")
            lines.append(
                f"  {len(self.lnt_file.textures)} texture region(s) "
                f"resolved")
            lines.append(
                f"  {len(self.lnt_file.tga_by_stem)} .tga file(s) loaded "
                f"(by filename stem)")
        messagebox.showinfo("Loaded file info", "\n".join(lines))

    def save_sd(self):
        if not self.sdxml:
            messagebox.showinfo("No file", "Open a .sd.xml first.")
            return
        if not messagebox.askyesno(
                "Save .sd.xml",
                f"Write edited coordinates back to:\n{self.sdxml.path}\n\n"
                "A .bak copy will be created."):
            return
        try:
            bak = self.sdxml.path.with_suffix(self.sdxml.path.suffix + ".bak")
            if not bak.exists():
                shutil.copy2(self.sdxml.path, bak)
            self.sdxml.save()
            self.status.config(
                text=f"Saved {self.sdxml.path.name} (backup: {bak.name})")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    # ------------------------------------------------------------------
    def about(self):
        messagebox.showinfo(
            "About",
            f"{APP} {VERSION}\n\n"
            "A visual tool for Rome: Total War UI modding.\n\n"
            "Start by clicking 'Pick mod folder…' and pointing at the\n"
            "folder that contains data/ (e.g. test_projects/project1).\n"
            "The tool will find the .lnt, the .sd.xml packs, the .tga\n"
            "files under data/menu/ and data/menu/textures/, and the\n"
            "<texture> blocks inside the .lnt itself.\n\n"
            "Menu (LNT) pieces without matching artwork are rendered as\n"
            "centered gold serif text, approximating the game's look.")

    def help_rtw(self):
        messagebox.showinfo(
            "How RTW UI files work",
            "Rome: Total War UI files\n"
            "─────────────────────────\n\n"
            ".sd.xml files list 'pages' (TGA atlas files) and 'sprites'.\n"
            "A sprite's x/y/w/h describe where IN THE TGA the sprite lives.\n"
            "They are NOT on-screen positions.  Used for the in-game\n"
            "campaign/battle HUD.\n\n"
            "The .lnt file DOES contain real on-screen coordinates for\n"
            "menu screens.  It also contains <texture> blocks that name\n"
            "individual .tga files under data/menu/ or\n"
            "data/menu/textures/.  Each <texture> has one or more\n"
            "<region> sub-blocks; the region name matches an <UI piece>\n"
            "name, and its left/top/right/bottom define the crop to use\n"
            "for that piece.  The tool loads those crops and renders\n"
            "the menu canvas with them.\n\n"
            "Pieces that have no matching artwork are drawn as centered\n"
            "gold serif text — a good approximation of how the game\n"
            "renders pure-text menu buttons.\n\n"
            "To see .lnt edits in-game, the modified .lnt must live in\n"
            "the mod's data/menu/ folder (with the game launched via\n"
            "-mod:<folder>).\n\n"
            "QUICK START:\n"
            "  Click 'Pick mod folder…' and point at the folder that\n"
            "  contains data/ (e.g. test_projects/project1).")


def main():
    try:
        ttk.Style().theme_use("clam")
    except Exception:
        pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
