#!/usr/bin/env python3

import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QMainWindow, QFrame, QVBoxLayout, QWidget
)

from bus import BusPanel
from menu import MenuPanel
from qr import QRCodeCard


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dashboard")
        self.setFont(QFont("Arial", 20))
        #self.resize(1000, 500)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Left side: departure board (bus.py) + QR card (qr.py)
        left = QVBoxLayout()
        self.bus_panel = BusPanel()
        left.addWidget(self.bus_panel)
        left.addStretch()
        self.qrCodeCard = QRCodeCard()

        #seperator line
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Plain)
        layout.addWidget(separator)
        left.addWidget(separator)
        left.addWidget(self.qrCodeCard)

        layout.addLayout(left, 2)

        #seperator line
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Plain)
        layout.addWidget(separator)

        # Right side: Mensa (menu.py)
        self.menu_panel = MenuPanel()
        layout.addWidget(self.menu_panel, 3)

app = QApplication(sys.argv)
app.setApplicationName("dashboard")
window = MainWindow()
window.show()
QTimer.singleShot(200, window.showFullScreen)
sys.exit(app.exec())