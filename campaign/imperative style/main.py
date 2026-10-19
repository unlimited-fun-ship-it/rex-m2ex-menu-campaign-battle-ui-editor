#!/usr/bin/env python3
import sys
from PyQt5.QtWidgets import QApplication
from campaign_hud_editor import create_main_window

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = create_main_window()
    window.show()
    sys.exit(app.exec_())