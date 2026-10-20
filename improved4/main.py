#!/usr/bin/env python3
import sys
from PyQt5.QtWidgets import QApplication

import config

if __name__ == "__main__":
    config.setup_logging()
    app = QApplication(sys.argv)
    from editor import MainWindow
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
