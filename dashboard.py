
#!/usr/bin/env python3

import sys
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

from PySide6.QtCore import QStandardPaths, QThread, QTimer, Signal, Qt, QUrl
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QApplication, QGridLayout, QHBoxLayout, QLabel, QMainWindow,
    QFrame, QSizePolicy, QVBoxLayout, QWidget
)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkDiskCache, QNetworkRequest, QNetworkReply

from rvv import get_departures, parse_time
from stwno import get_menu

TIMEZONE = ZoneInfo("Europe/Berlin")
BUS_REFRESH_MS = 60*1000 #1 Minute 
MENU_REFRESH_MS = 1 * 60 * 1000  # 1 Minute, only updates if the date or mensa_id changes, so this is fine
MENU_REFRESH_FORCE_MS = 60*60*1000 # force a menu refresh every hour
MENSA_OPENING_DAYS = range(0, 5) # Monday = 0 to Friday = 4
MENSA_CLOSING_TIME = time(14,15) # 14:15
ABENDMENSA_OPENING_DAYS = range(0,4)# Monday = 0 to Thursday = 3
ABENDMENSA_CLOSING_TIME = time(19,0)# 19:00
BUS_STOP_ID = "de:09362:14080" # Universität
BUS_AMOUNT = 11 # Max future departures to show


class BusFetchWorker(QThread):
    result_ready = Signal(object)
    error_occurred = Signal(str)

    def run(self):
        try:
            self.result_ready.emit(get_departures(BUS_STOP_ID, BUS_AMOUNT))
        except Exception as exc:
            self.error_occurred.emit(str(exc))

class MenuFetchWorker(QThread):
    result_ready = Signal(object, str, str)
    error_occurred = Signal(str)

    def __init__(self, date, mensa_key, mensa_name, parent=None):
        super().__init__(parent)
        self.date = date
        self.mensa_key = mensa_key
        self.mensa_name = mensa_name

    def run(self):
        try:
            self.result_ready.emit(get_menu(self.date, location=self.mensa_key), self.date, self.mensa_name)
        except Exception as exc:
            self.error_occurred.emit(str(exc))



class DishCard(QFrame):
    def __init__(self, dish, network, dish_count, parent=None):
        super().__init__(parent)
        self.dish_count = dish_count
        self.og_pixmap = None
        self.setObjectName("dishCard")
        self.setStyleSheet("""
            QFrame#dishCard {
                background: palette(base);
                border: 1px solid palette(mid);
                border-radius: 9px;
            }
            QLabel {
                border: none;
            }
            QLabel#dishName {
                font-size: 20px;
                font-weight: 600;
            }
            QLabel#dishPrice {
                font-size: 18px;
                font-weight: 500
            }
            QLabel#dishType {
                font-size: 18px;
                color: #18794e;
            }
            QLabel#dishAllergens {
                font-size: 12x;
                color: palette(placeholder-text);
            }
        """)

        layout = QVBoxLayout(self)
        #layout.setContentsMargins(6, 6, 6, 6)
        #layout.setSpacing(7)
        name = QLabel(dish.get("name", "Unbekannt"))
        name.setObjectName("dishName")
        name.setWordWrap(True)
        layout.addWidget(name)

        content = QHBoxLayout()

        self.picture = QLabel("🍽")
        self._calculate_image_height()
        # the images have a 3:2 aspect ratio, so scale them correclty
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.picture.setStyleSheet(
            "background: palette(alternate-base); border-radius: 6px;"
        )
        content.addWidget(self.picture,  0, Qt.AlignmentFlag.AlignTop)

        details = QVBoxLayout()
        #details.setSpacing(3)
        kind_layout = QHBoxLayout()
        if dish.get("type"):
            kind = QLabel(dish["type"])
            kind.setObjectName("dishType")
            kind_layout.addWidget(kind)
        #consistent layou
        else: 
            kind_layout.addWidget(QLabel(""))
        if dish.get("allergens"):
            allergens_label = QLabel(", ".join(dish["allergens"]))
            allergens_label.setObjectName("dishAllergens")
            kind_layout.addWidget(allergens_label)
        details.addLayout(kind_layout)
        price = QLabel(dish.get("price", ""))
        price.setObjectName("dishPrice")
        details.addWidget(price)

        details.addStretch()
        content.addLayout(details, 1)


        layout.addLayout(content)
        if dish.get("image"):
            request = QNetworkRequest(QUrl(dish["image"]))
            #use cache
            request.setAttribute(
             QNetworkRequest.Attribute.CacheLoadControlAttribute,
             QNetworkRequest.CacheLoadControl.PreferCache,
              )
            reply = network.get(request)
            reply.setParent(self)
            reply.finished.connect(
                lambda r=reply: self._image_loaded(r)
            )

    def _calculate_image_height(self):
            self.img_height = 64
            if self.dish_count != 0:
                self.img_height = int(((self.window().height())/self.dish_count * 0.8))
            self.picture.setFixedSize(int(self.img_height*3/2), self.img_height)

    def rescale_image(self):
        self._calculate_image_height()
        if  self.og_pixmap:
            self.picture.setPixmap(
                                self.og_pixmap.scaled(
                                    self.picture.size(),
                                    Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation,
                                ))

    def _image_loaded(self, reply):
        if reply.error() == QNetworkReply.NetworkError.NoError:
            pixmap = QPixmap()
            if pixmap.loadFromData(reply.readAll().data()):
                self.og_pixmap = pixmap
                self.picture.setPixmap(
                    self.og_pixmap.scaled(
                        self.picture.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        reply.deleteLater()



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
        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.setInterval(150)
        self.resize_timer.timeout.connect(self.resize_menu)
        self.setWindowTitle("Dashboard")
        self.setFont(QFont("Arial", 20))
        #self.resize(1000, 500)

        self.Busworker = None
        self.menu_worker = None
        self.last_date = None 
        self.last_mensa_key = None

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)

        # Left side: departure board
        left = QVBoxLayout()
        left.setSpacing(6)
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

        layout.addLayout(left, 2)

        #seperator line
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Plain)
        layout.addWidget(separator)

        # Right side
        
        # Right side: Mensa
        
        # Mensa: no scroll area
        right = QVBoxLayout()
        right.setSpacing(6)

        self.menu_title = QLabel("Mensa")
        self.menu_title.setStyleSheet("font-size: 26px; font-weight: 700;")
        self.menu_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(self.menu_title)
        self.menu_status = QLabel("Speiseplan")
        self.menu_status.setStyleSheet(
            "color: palette(placeholder-text); font-size: 14px;"
        )
        self.menu_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(self.menu_status)

        self.menu_content = QWidget()
        self.menu_content.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)
        self.menu_grid = QGridLayout(self.menu_content)
        self.menu_grid.setContentsMargins(0, 0, 0, 0)
        self.menu_grid.setHorizontalSpacing(7)
        self.menu_grid.setVerticalSpacing(6)
        self.menu_grid.setColumnStretch(0, 1)
        self.menu_grid.setColumnStretch(1, 1)

        right.addWidget(self.menu_content, 1)

        self.image_network = QNetworkAccessManager(self)
        cache = QNetworkDiskCache(self)
        cache_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
        cache.setCacheDirectory(cache_dir + "/images")
        cache.setMaximumCacheSize(100 * 1024 * 1024)   # 100 MB
        self.image_network.setCache(cache)

        layout.addLayout(right, 3)


        self.bus_timer = QTimer(self)
        self.bus_timer.timeout.connect(self.refreshBus)
        self.bus_timer.start(BUS_REFRESH_MS)

        self.bus_heading_timer = QTimer(self)
        self.bus_heading_timer.timeout.connect(self.update_bus_heading)
        self.bus_heading_timer.start(1000)

        self.menu_timer = QTimer(self)
        self.menu_timer.timeout.connect(self.refreshMenu)
        self.menu_timer.start(MENU_REFRESH_MS)

        self.menu_force_timer = QTimer(self)
        self.menu_force_timer.timeout.connect(lambda: self.refreshMenu(force=True))
        self.menu_force_timer.start(MENU_REFRESH_FORCE_MS)
        self.update_bus_heading()
        self.refreshMenu()
        self.refreshBus()


    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resize_timer.start()

    def refreshMenu(self, force=False):
        if self.menu_worker is not None:
                    return # only one instance

        date = datetime.now(TIMEZONE)
        mensa_key = "UNI-R"
        mensa_name = "Mensa"

        def next_opening_day(d, opening_days):
            max_its = 7 # one week
            i = 0
            # run once to skip atleast one day ahead
            d = d +  timedelta(days=1)
            while d.weekday() not in opening_days and i < max_its:
                i += 1
                d = d +  timedelta(days=1)
            return d
        
        #mensa closed on weekends, show menu on opening days
        if date.weekday() not in MENSA_OPENING_DAYS and date.weekday() not in ABENDMENSA_OPENING_DAYS:
            date = next_opening_day(date, MENSA_OPENING_DAYS)

        #past opening time of normal mensa
        elif date.time() > MENSA_CLOSING_TIME:
            #Abendmensa opening time
            if date.time() <= ABENDMENSA_CLOSING_TIME and date.weekday() in ABENDMENSA_OPENING_DAYS:
                mensa_key = "HS-R-abend"
                mensa_name = "Abendmensa"

            #Show mensa for the next open days
            else:
                date = next_opening_day(date, MENSA_OPENING_DAYS)

        date = date.strftime("%Y-%m-%d")
        if not force and self.last_date == date and self.last_mensa_key == mensa_key:
            #Same data requested as last time, so we dont have to to anything.
            return
        # save last requested data
        self.last_date = date
        self.last_mensa_key = mensa_key

        self.menu_status.setText("Aktualisiere Speiseplan …")
        menu_worker = MenuFetchWorker(date, mensa_key, mensa_name, self)
        menu_worker.result_ready.connect(self.update_menu)
        menu_worker.error_occurred.connect(self.show_menu_error)
        menu_worker.finished.connect(menu_worker.deleteLater)
        menu_worker.finished.connect(self._menu_worker_done)
        self.menu_worker = menu_worker
        menu_worker.start()

    def _menu_worker_done(self):
        self.menu_worker = None

    def resize_menu(self):
        for i in range(0, self.menu_grid.count()): 
          item = self.menu_grid.itemAt(i).widget()
          if isinstance(item, DishCard):
              item.rescale_image()

    def update_menu(self, menu, date, mensa_name):
        self.menu_title.setText(f"{mensa_name} am {datetime.strptime(date, "%Y-%m-%d").strftime("%d.%m.%Y")}")
        while self.menu_grid.count():
            item = self.menu_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        sections = [
            ("Suppen", "soups"),
            ("Hauptgerichte", "mains"),
            ("Beilagen", "sides"),
            ("Nachspeisen", "deserts"),
        ]

        row = 0
        count = 0
        for title, key in sections:
                    dishes = menu.get(key, [])
                    count += len(dishes)

        for title, key in sections:
            dishes = menu.get(key, [])
            if not dishes:
                continue

            heading = QLabel(title)
            heading.setStyleSheet(
                "font-size: 25px; font-weight: 700; padding-top: 3px;"
            )
            self.menu_grid.addWidget(heading, row, 0, 1, 2)
            row += 1

            for i in range(0, len(dishes), 2):
                for col, dish in enumerate(dishes[i:i + 2]):
                    self.menu_grid.addWidget(
                        DishCard(dish, self.image_network, count),
                        row,
                        col,
                    )
                row += 1
        self.menu_status.setText(
                            f"{count} Gerichte · "
                            f"Aktualisiert {datetime.now(TIMEZONE):%H:%M:%S}"
                        )
        #resize correctly on first run
        self.resize_timer.start()

    def set_status(self, label, text, max_len=70):
        """Set label text without letting long text change the layout size."""
        #label.setToolTip(text)  # full text still available on hover
        label.setText(text if len(text) <= max_len else text[:max_len - 1] + "…")

    def show_menu_error(self, message):
        #Reset these keys so we can try again    
        self.last_date = None
        self.last_mensa_key = None
        self.dish_count = 0 # no dishes
        self.set_status(self.menu_status, f"Speiseplan-Fehler: {message}")
        self.resize_timer.start()

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
