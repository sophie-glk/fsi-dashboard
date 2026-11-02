"""Bus departures: data fetching, departure cards and the complete bus panel."""

from datetime import datetime
import time
from zoneinfo import ZoneInfo

from PySide6.QtCore import QThread, QTimer, Signal, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from rvv import get_departures, parse_time

REFRESH_AFTER_RESIZE_MS = 2000  # wait for main thread to finish initializing the window before refreshing, otherwise the window height is too small and not enough departures are shown
TIMEZONE = ZoneInfo("Europe/Berlin")
BUS_REFRESH_MS = 60 * 1000  # 1 Minute
BUS_STOP_ID = "de:09362:14080"  # Universität
MAX_BUS_AMOUNT = 10  # Max future departures to show


class BusFetchWorker(QThread):
    def __init__(self, window_size, parent=None):
        super().__init__(parent)
        self.window_size = window_size

    result_ready = Signal(object)
    error_occurred = Signal(str)

    def run(self):
        try:
            amount = min(MAX_BUS_AMOUNT, int(self.window_size/65))
            self.result_ready.emit(get_departures(BUS_STOP_ID, amount))
        except Exception as exc:
            self.error_occurred.emit(str(exc))


class DepartureCard(QFrame):
    def __init__(self, result, parent=None):
        super().__init__(parent)
        self.setObjectName("departureCard")

        self.setStyleSheet("""
            QFrame#departureCard {
                background: rgba(128, 128, 128, 0.07);
                border: 1px solid rgba(128, 128, 128, 0.15);
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
        if delay > 0 and estimated:
            time_text = estimated.strftime("%H:%M")

        time_col = QVBoxLayout()
        time_label = QLabel(time_text)
        time_label.setObjectName("time")
        time_label.setMinimumWidth(80)
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


class BusPanel(QWidget):
    """Heading with clock, status line, list of departures and refresh timers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bus_worker = None
        self.departure_count = 0
        self.last_update = 0

        layout = QVBoxLayout(self)
        
        self.bus_heading = QLabel("Busse")
        self.bus_heading.setStyleSheet("font-size: 26px; font-weight: 700;")
        font = self.bus_heading.font()
        font.setStyleStrategy(QFont.StyleStrategy.PreferDefault)
        font.setFeature(QFont.Tag("tnum"), 1)  # tabular numbers, all digits have the same width, needed for the clock
        self.bus_heading.setFont(font)
        self.bus_heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.bus_heading)

        self.status = QLabel("Lade Abfahrten …")
        self.status.setStyleSheet(
            "color: palette(placeholder-text); font-size: 12px;"
        )
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status)

        self.departure_list = QVBoxLayout()
        self.departure_list.setSpacing(7)
        layout.addLayout(self.departure_list)

        self.bus_timer = QTimer(self)
        self.bus_timer.timeout.connect(self.refresh)
        self.bus_timer.start(BUS_REFRESH_MS)

        self.bus_heading_timer = QTimer(self)
        self.bus_heading_timer.timeout.connect(self.update_heading)
        self.bus_heading_timer.start(1000)

        self.update_heading()
        #wait for main thread to finish initializing the window before refreshing, otherwise the window height is too small and not enough departures are shown
        QTimer.singleShot(REFRESH_AFTER_RESIZE_MS, self.refresh)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(REFRESH_AFTER_RESIZE_MS, self.refresh) # refresh the departures when the window is resized, to show more or less departures
        
    def refresh(self):
        # Never start a second request while one is running.
        if self.bus_worker is not None:  # a request is still in flight
            return
        if time.time() - self.last_update < 10:  # don't refresh more than once every 10 seconds
            return
        self.status.setText("Aktualisiere ...")
        worker = BusFetchWorker(self.window().height(), self)
        worker.result_ready.connect(self.update_departures)
        worker.error_occurred.connect(self.show_error)
        worker.finished.connect(self._worker_done)
        worker.finished.connect(worker.deleteLater)
        self.bus_worker = worker
        worker.start()

    def _worker_done(self):
        self.last_update = time.time()
        self.status.setText(
                    f"{self.departure_count} Abfahrten insgesamt · "
                    f"Aktualisiert {datetime.now(TIMEZONE):%H:%M:%S}"
                )
        self.bus_worker = None

    def update_heading(self):
        now = datetime.now(TIMEZONE).strftime("%H:%M:%S")
        self.bus_heading.setText(f"Busfahrplan um {now} Uhr")

    def update_departures(self, results):
        while self.departure_list.count():
            item = self.departure_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for result in results:
            self.departure_list.addWidget(DepartureCard(result))

        if not results:
            self.departure_list.addWidget(QLabel("Keine Abfahrten gefunden"))
        self.departure_count = len(results)

    def show_error(self, message):
        text = f"Fehler: {message}"
        max_len = 70  # keep long text from changing the layout size
        self.status.setText(text if len(text) <= max_len else text[:max_len - 1] + "…")
