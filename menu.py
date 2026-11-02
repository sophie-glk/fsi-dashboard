"""Mensa menu: data fetching, dish cards and the complete menu panel."""

from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

from PySide6.QtCore import QStandardPaths, QThread, QTimer, Signal, Qt, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget
)
from PySide6.QtNetwork import (
    QNetworkAccessManager, QNetworkDiskCache, QNetworkRequest, QNetworkReply
)
from torch import layout

from stwno import get_menu

TIMEZONE = ZoneInfo("Europe/Berlin")
MENU_REFRESH_MS = 1 * 60 * 1000  # 1 Minute, only updates if the date or mensa_id changes, so this is fine
MENU_REFRESH_FORCE_MS = 60 * 60 * 1000  # force a menu refresh every hour
MENSA_OPENING_DAYS = range(0, 5)  # Monday = 0 to Friday = 4
MENSA_CLOSING_TIME = time(14, 15)  # 14:15
ABENDMENSA_OPENING_DAYS = range(0, 4)  # Monday = 0 to Thursday = 3
ABENDMENSA_CLOSING_TIME = time(19, 0)  # 19:00


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
            self.result_ready.emit(
                get_menu(self.date, location=self.mensa_key), self.date, self.mensa_name
            )
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
                background: rgba(128, 128, 128, 0.07);
                border: 1px solid rgba(128, 128, 128, 0.15);
                border-radius: 5px;
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
                font-weight: 500;
            }
            QLabel#dishType {
                font-size: 18px;
                color: #18794e;
            }
            QLabel#dishAllergens {
                font-size: 10px;
                color: palette(placeholder-text);
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)
        name = QLabel(dish.get("name", "Unbekannt"))
        name.setObjectName("dishName")
        name.setWordWrap(True)
        layout.addWidget(name)

        content = QHBoxLayout()
        content.setSpacing(8)
        self.picture = QLabel("🍽")
        self._calculate_image_height()
        # the images have a 3:2 aspect ratio, so scale them correctly
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.picture.setStyleSheet(
            "background: palette(alternate-base); border-radius: 6px;"
        )
        content.addWidget(self.picture, 0, Qt.AlignmentFlag.AlignTop)

        details = QVBoxLayout()
        if dish.get("type"):
            kind = QLabel(dish["type"])
            kind.setObjectName("dishType")
            details.addWidget(kind)
        # consistent layout
        else:
            details.addWidget(QLabel(""))
        if dish.get("allergens"):
            allergens_label = QLabel(", ".join(dish["allergens"]))
            allergens_label.setAlignment(Qt.AlignmentFlag.AlignTop)
            allergens_label.setObjectName("dishAllergens")
            details.addWidget(allergens_label)
        else:
            details.addWidget(QLabel(""))
        price = QLabel(dish.get("price", ""))
        price.setObjectName("dishPrice")
        price.setAlignment(Qt.AlignmentFlag.AlignTop)
        details.addWidget(price)
        details.addStretch(1)
        details.setSpacing(2)
        content.addLayout(details)

        layout.addLayout(content)
        if dish.get("image"):
            request = QNetworkRequest(QUrl(dish["image"]))
            # use cache
            request.setAttribute(
                QNetworkRequest.Attribute.CacheLoadControlAttribute,
                QNetworkRequest.CacheLoadControl.PreferCache,
            )
            reply = network.get(request)
            reply.setParent(self)
            reply.finished.connect(lambda r=reply: self._image_loaded(r))

    def _calculate_image_height(self):
        self.img_height = 64
        if self.dish_count != 0:
            self.img_height = int((self.window().height() / self.dish_count * 0.8 ))
        self.picture.setFixedSize(int(self.img_height * 3 / 2), self.img_height)

    def rescale_image(self):
        self._calculate_image_height()
        if self.og_pixmap:
            self.picture.setPixmap(
                self.og_pixmap.scaled(
                    self.picture.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

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


class MenuPanel(QWidget):
    """The whole right-hand side: title, status line, dish grid, timers."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.menu_worker = None
        self.last_date = None
        self.last_mensa_key = None

        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.setInterval(150)
        self.resize_timer.timeout.connect(self.resize_menu)

        right = QVBoxLayout(self)

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

        # Mensa: no scroll area
        self.menu_content = QWidget()
        self.menu_content.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored
        )
        self.menu_grid = QGridLayout(self.menu_content)
        self.menu_grid.setContentsMargins(0, 0, 0, 0)
        self.menu_grid.setHorizontalSpacing(6)
        self.menu_grid.setVerticalSpacing(3)
        self.menu_grid.setColumnStretch(0, 1)
        self.menu_grid.setColumnStretch(1, 1)
        right.addWidget(self.menu_content, 1)

        self.image_network = QNetworkAccessManager(self)
        cache = QNetworkDiskCache(self)
        cache_dir = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.CacheLocation
        )
        cache.setCacheDirectory(cache_dir + "/images")
        cache.setMaximumCacheSize(100 * 1024 * 1024)  # 100 MB
        self.image_network.setCache(cache)

        self.menu_timer = QTimer(self)
        self.menu_timer.timeout.connect(self.refresh)
        self.menu_timer.start(MENU_REFRESH_MS)

        self.menu_force_timer = QTimer(self)
        self.menu_force_timer.timeout.connect(lambda: self.refresh(force=True))
        self.menu_force_timer.start(MENU_REFRESH_FORCE_MS)

        self.refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resize_timer.start()

    @staticmethod
    def _next_opening_day(d, opening_days):
        max_its = 7  # one week
        i = 0
        # run once to skip at least one day ahead
        d = d + timedelta(days=1)
        while d.weekday() not in opening_days and i < max_its:
            i += 1
            d = d + timedelta(days=1)
        return d

    def refresh(self, force=False):
        if self.menu_worker is not None:
            return  # only one instance

        date = datetime.now(TIMEZONE)
        mensa_key = "UNI-R"
        mensa_name = "Mensa"

        # mensa closed on weekends, show menu on opening days
        if (date.weekday() not in MENSA_OPENING_DAYS
                and date.weekday() not in ABENDMENSA_OPENING_DAYS):
            date = self._next_opening_day(date, MENSA_OPENING_DAYS)

        # past opening time of normal mensa
        elif date.time() > MENSA_CLOSING_TIME:
            # Abendmensa opening time
            if (date.time() <= ABENDMENSA_CLOSING_TIME
                    and date.weekday() in ABENDMENSA_OPENING_DAYS):
                mensa_key = "HS-R-abend"
                mensa_name = "Abendmensa"
            # Show mensa for the next open days
            else:
                date = self._next_opening_day(date, MENSA_OPENING_DAYS)

        date = date.strftime("%Y-%m-%d")
        if not force and self.last_date == date and self.last_mensa_key == mensa_key:
            # Same data requested as last time, so we don't have to do anything.
            return
        # save last requested data
        self.last_date = date
        self.last_mensa_key = mensa_key

        self.menu_status.setText("Aktualisiere Speiseplan …")
        worker = MenuFetchWorker(date, mensa_key, mensa_name, self)
        worker.result_ready.connect(self.update_menu)
        worker.error_occurred.connect(self.show_error)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(self._worker_done)
        self.menu_worker = worker
        worker.start()

    def _worker_done(self):
        self.menu_worker = None

    def resize_menu(self):
        for i in range(self.menu_grid.count()):
            item = self.menu_grid.itemAt(i).widget()
            if isinstance(item, DishCard):
                item.rescale_image()

    def update_menu(self, menu, date, mensa_name):
        pretty_date = datetime.strptime(date, "%Y-%m-%d").strftime("%d.%m.%Y")
        self.menu_title.setText(f"{mensa_name} am {pretty_date}")
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

        count = sum(len(menu.get(key, [])) for _, key in sections)

        row = 0
        for title, key in sections:
            dishes = menu.get(key, [])
            if not dishes:
                continue

            heading = QLabel(title)
            heading.setStyleSheet(
                "font-size: 25px; font-weight: 700; padding-top: 3px;"
            )
            self.menu_grid.addWidget(heading, row, 0, 1, 2)
            self.menu_grid.setRowStretch(row, 2) # increase spacing between sections
            row += 1

            for i in range(0, len(dishes), 2):
                for col, dish in enumerate(dishes[i:i + 2]):
                    self.menu_grid.addWidget(
                        DishCard(dish, self.image_network, count), row, col
                    )
                row += 1
        self.menu_grid.setRowStretch(row, 1)  # push everything up
        self.menu_status.setText(
            f"{count} Gerichte · "
            f"Aktualisiert {datetime.now(TIMEZONE):%H:%M:%S}"
        )
        # resize correctly on first run
        self.resize_timer.start()

    def show_error(self, message):
        # Reset these keys so we can try again
        self.last_date = None
        self.last_mensa_key = None
        text = f"Speiseplan-Fehler: {message}"
        max_len = 70
        self.menu_status.setText(text if len(text) <= max_len else text[:max_len - 1] + "…")
        self.resize_timer.start()
