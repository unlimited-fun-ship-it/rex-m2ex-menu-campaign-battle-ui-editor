#!/usr/bin/env python3
import sys
from PyQt5.QtWidgets import QApplication
from campaign_hud_editor import HUDEditor

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = HUDEditor()
    window.show()
    sys.exit(app.exec_())