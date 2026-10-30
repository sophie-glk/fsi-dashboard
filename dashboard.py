#!/usr/bin/env python3

import fcntl
import io
import socket
import struct
import sys
import qrcode

from PySide6.QtCore import QThread, QTimer, Signal, Qt
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMainWindow,
    QFrame, QVBoxLayout, QWidget
)

from bus import BusPanel
from menu import MenuPanel

LAN_INTERFACE = "enp39s0"
QR_UPDATE_TIME = 1*60*1000 # 1 minute
QR_CODE_SIZE = 150


class QRFetchWorker(QThread):
    result_ready = Signal(object)
    error_occurred = Signal(str)

    def run(self):
        try:
            self.result_ready.emit(get_ip_address(LAN_INTERFACE))
        except Exception as exc:
            self.error_occurred.emit(str(exc))

def get_ip_address(ifname):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        return socket.inet_ntoa(fcntl.ioctl(
            s.fileno(),
            0x8915,  # SIOCGIFADDR
            struct.pack('256s', ifname[:15].encode())
        )[20:24])


class QRCodeCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.link = ""
        layout = QVBoxLayout(self)
        self.setObjectName("QRCodeCard")
        self.setStyleSheet("""
                QFrame#QRCodeCard {
                    background: palette(base);
                    border: 1px solid palette(mid);
                    border-radius: 9px;
                }
                QLabel {
                    border: none;
                }
                QLabel#title {
                    font-size: 24px;
                    font-weight: 700;
                }
                QLabel#text {
                    font-size: 22px;
                    font-weight: 500;
                }
                QLabel#qrcode {
                    font-size: 22px;
                    font-weight: 500;
                }
                QLabel#error {
                    font-size: 14px;
                    font-weight: 300;
                }

            """)
        title = "Strichliste (TEST ONLY) - EDUROAM NEEDED"
        self.titleLabel  = QLabel(title)
        self.errorLabel = QLabel("")
        self.errorLabel.setObjectName("error")
        self.titleLabel.setObjectName("title")
        self.textLabel = QLabel("")
        self.textLabel.setObjectName("text")
        self.codeLabel = QLabel("QR-Code")
        self.codeLabel.setObjectName("qrcode")
        self.codeLabel.setFixedHeight(QR_CODE_SIZE)
        layout.addWidget(self.titleLabel)
        qr_layout = QHBoxLayout()
        qr_layout.addWidget(self.codeLabel)
        qr_layout.addWidget(self.textLabel)
        layout.addLayout(qr_layout)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dashboard")
        self.setFont(QFont("Arial", 20))
        #self.resize(1000, 500)

        self.QRWorker = None

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Left side: departure board (everything lives in bus.py) + QR card
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

        # Right side: Mensa (everything lives in menu.py)
        self.menu_panel = MenuPanel()
        layout.addWidget(self.menu_panel, 3)

        self.qr_timer = QTimer(self)
        self.qr_timer.timeout.connect(self.refreshQRCode)
        self.qr_timer.start(QR_UPDATE_TIME)

        self.refreshQRCode()

    def set_status(self, label, text, max_len=70):
        """Set label text without letting long text change the layout size."""
        label.setText(text if len(text) <= max_len else text[:max_len - 1] + "…")

    def refreshQRCode(self):
        if self.QRWorker is not None:
            return
        worker = QRFetchWorker(self)
        worker.result_ready.connect(self.update_QRCode)
        worker.error_occurred.connect(lambda m: self.set_status(self.qrCodeCard.errorLabel, m))
        worker.finished.connect(self._qr_worker_done)
        worker.finished.connect(worker.deleteLater)
        self.QRWorker = worker
        worker.start()

    def _qr_worker_done(self):
        self.QRWorker = None

    def update_QRCode(self, ip_address):
        card = self.qrCodeCard
        link = f"http://{ip_address}"
        if card.link == link:
            #nothing changed
            return
        card.link = link
        buffer = io.BytesIO()
        qrcode.make(card.link).save(buffer, "PNG")
        pixmap = QPixmap()
        pixmap.loadFromData(buffer.getvalue(), "PNG")
        card.textLabel.setText(card.link)
        card.codeLabel.setPixmap(
            pixmap.scaled(
                card.codeLabel.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

app = QApplication(sys.argv)
app.setApplicationName("dashboard")
window = MainWindow()
window.show()
QTimer.singleShot(200, window.showFullScreen)
sys.exit(app.exec())