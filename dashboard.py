#!/usr/bin/env python3

import fcntl
import io
import socket
import struct
import sys
import qrcode
from datetime import datetime
from zoneinfo import ZoneInfo

from PySide6.QtCore import QThread, QTimer, Signal, Qt
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMainWindow,
    QFrame, QVBoxLayout, QWidget
)

from rvv import get_departures, parse_time
from menu import MenuPanel

TIMEZONE = ZoneInfo("Europe/Berlin")
BUS_REFRESH_MS = 60*1000 #1 Minute 
BUS_STOP_ID = "de:09362:14080" # Universität
BUS_AMOUNT = 10 # Max future departures to show
LAN_INTERFACE = "enp39s0"
QR_UPDATE_TIME = 1*60*1000 # 1 minute
QR_CODE_SIZE = 150

class BusFetchWorker(QThread):
    result_ready = Signal(object)
    error_occurred = Signal(str)

    def run(self):
        try:
            self.result_ready.emit(get_departures(BUS_STOP_ID, BUS_AMOUNT))
        except Exception as exc:
            self.error_occurred.emit(str(exc))

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

class DepartureCard(QFrame):
    def __init__(self, result, parent=None):
        super().__init__(parent)
        self.setObjectName("departureCard")

        self.setStyleSheet("""
            QFrame#departureCard {
                background: palette(base);
                border: 1px solid palette(mid);
                border-radius: 9px;
            }
            QLabel {
                border: none;
            }
            QLabel#time {
                font-size: 24px;
                font-weight: 700;
            }
            QLabel#line {
                background: #dceafe;
                color: #174ea6;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 20px;
                font-weight: 700;
            }
            QLabel#destination {
                font-size: 20px;
                font-weight: 600;
            }
            QLabel#platform {
                font-size: 20px;
                font-weight: 600;
            }
            QLabel#muted {
                font-size: 15px;
                color: palette(placeholder-text);
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(12)

        planned = parse_time(result["time"])
        estimated = parse_time(result["estimated"])
        delay = result.get("delay", 0) or 0

        time_text = planned.strftime("%H:%M") if planned else "?"
        if  delay > 0 and estimated:
            time_text = estimated.strftime("%H:%M")

        time_col = QVBoxLayout()
        time_label = QLabel(time_text)
        time_label.setObjectName("time")
        time_col.addWidget(time_label)

        if delay > 0:
            delay_label = QLabel(f"+{delay} min")
            delay_label.setStyleSheet(
                "color: #c2410c; font-size: 15px; font-weight: 600;"
            )
        else:
            delay_label = QLabel("Pünktlich")
            delay_label.setStyleSheet(
                "color: #16803d; font-size: 15px;"
            )
        time_col.addWidget(delay_label)
        layout.addLayout(time_col)

        line = QLabel(str(result["line"]))
        line.setObjectName("line")
        line.setAlignment(Qt.AlignmentFlag.AlignCenter)
        line.setMinimumWidth(42)
        layout.addWidget(line)

        destination_col = QVBoxLayout()
        destination = QLabel(str(result["destination"]))
        destination.setObjectName("destination")
        destination.setWordWrap(True)
        destination_col.addWidget(destination)
        layout.addLayout(destination_col, 1)

        platform_col = QVBoxLayout()
        platform = QLabel(f"{result['platform']}")
        platform.setObjectName("platform")
        platform_col.addWidget(platform)
        layout.addLayout(platform_col)



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dashboard")
        self.setFont(QFont("Arial", 20))
        #self.resize(1000, 500)

        self.Busworker = None
        self.QRWorker = None

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0) 
        layout.setSpacing(0)   
        # Left side: departure board
        left = QVBoxLayout()

        self.bus_heading =  QLabel("Busse")
        self.bus_heading.setStyleSheet("font-size: 26px; font-weight: 700;")
        font = self.bus_heading.font()
        font.setStyleStrategy(QFont.StyleStrategy.PreferDefault)
        font.setFeature(QFont.Tag("tnum"), 1)   # tabular numbers,all digits have the same size, needed for the clcok
        self.bus_heading.setFont(font)
        self.bus_heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left.addWidget(self.bus_heading)
        self.status = QLabel("Lade Abfahrten …")
        self.status.setStyleSheet(
            "color: palette(placeholder-text); font-size: 12px;"
        )
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left.addWidget(self.status)
        self.departure_list = QVBoxLayout()
        self.departure_list.setSpacing(7)
        left.addLayout(self.departure_list)
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

        self.bus_timer = QTimer(self)
        self.bus_timer.timeout.connect(self.refreshBus)
        self.bus_timer.start(BUS_REFRESH_MS)

        self.bus_heading_timer = QTimer(self)
        self.bus_heading_timer.timeout.connect(self.update_bus_heading)
        self.bus_heading_timer.start(1000)

        self.qr_timer = QTimer(self)
        self.qr_timer.timeout.connect(self.refreshQRCode)
        self.qr_timer.start(QR_UPDATE_TIME)

        self.update_bus_heading()
        self.refreshBus()
        self.refreshQRCode()

    def set_status(self, label, text, max_len=70):
        """Set label text without letting long text change the layout size."""
        #label.setToolTip(text)  # full text still available on hover
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

    def refreshBus(self):
        # Never start a second request while one is running.
        if self.Busworker is not None:      # a request is still in flight
         return
        self.status.setText("Aktualisiere ...")
        worker = BusFetchWorker(self)
        worker.result_ready.connect(self.update_departures)
        worker.error_occurred.connect(self.show_error)
        worker.finished.connect(self._bus_worker_done)
        worker.finished.connect(worker.deleteLater)
        self.Busworker = worker
        worker.start()
        
    def _bus_worker_done(self):
        self.Busworker = None

    def update_bus_heading(self):
     now = datetime.now(TIMEZONE).strftime("%H:%M:%S")
     text = f"Busfahrplan um {now} Uhr"
     self.bus_heading.setText(text)
    
    def update_departures(self, results):
        while self.departure_list.count():
            item = self.departure_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        #update title which includes current time

        for result in results:
            self.departure_list.addWidget(DepartureCard(result))

        if not results:
            empty = QLabel("Keine Abfahrten gefunden")
            self.departure_list.addWidget(empty)

        self.status.setText(
            f"{len(results)} Abfahrten insgesamt · "
            f"Aktualisiert {datetime.now(TIMEZONE):%H:%M:%S}"
        )


    def show_error(self, message):
        self.set_status(self.status, f"Fehler: {message}")

app = QApplication(sys.argv)
app.setApplicationName("dashboard")
window = MainWindow()
window.show()
QTimer.singleShot(200, window.showFullScreen)
sys.exit(app.exec())