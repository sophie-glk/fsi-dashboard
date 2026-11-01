"""QR code card: looks up the LAN IP and shows it as link and QR code."""

import fcntl
import io
import socket
import struct

import qrcode
from PySide6.QtCore import QThread, QTimer, Signal, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

LAN_INTERFACE = "eth0"
QR_UPDATE_TIME = 1 * 60 * 1000  # 1 minute
QR_CODE_SIZE = 150


def get_ip_address(ifname):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        return socket.inet_ntoa(fcntl.ioctl(
            s.fileno(),
            0x8915,  # SIOCGIFADDR
            struct.pack('256s', ifname[:15].encode())
        )[20:24])


class QRFetchWorker(QThread):
    result_ready = Signal(object)
    error_occurred = Signal(str)

    def run(self):
        try:
            self.result_ready.emit(get_ip_address(LAN_INTERFACE))
        except Exception as exc:
            self.error_occurred.emit(str(exc))


class QRCodeCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.link = ""
        self.qr_worker = None

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
        self.titleLabel = QLabel(title)
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

        self.qr_timer = QTimer(self)
        self.qr_timer.timeout.connect(self.refresh)
        self.qr_timer.start(QR_UPDATE_TIME)

        self.refresh()

    def refresh(self):
        if self.qr_worker is not None:
            return
        worker = QRFetchWorker(self)
        worker.result_ready.connect(self.update_code)
        worker.error_occurred.connect(self.show_error)
        worker.finished.connect(self._worker_done)
        worker.finished.connect(worker.deleteLater)
        self.qr_worker = worker
        worker.start()

    def _worker_done(self):
        self.qr_worker = None

    def update_code(self, ip_address):
        link = f"http://{ip_address}"
        if self.link == link:
            # nothing changed
            return
        self.link = link
        buffer = io.BytesIO()
        qrcode.make(self.link).save(buffer, "PNG")
        pixmap = QPixmap()
        pixmap.loadFromData(buffer.getvalue(), "PNG")
        self.textLabel.setText(self.link)
        self.codeLabel.setPixmap(
            pixmap.scaled(
                self.codeLabel.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def show_error(self, message, max_len=70):
        # keep long text from changing the layout size
        self.errorLabel.setText(
            message if len(message) <= max_len else message[:max_len - 1] + "…"
        )
