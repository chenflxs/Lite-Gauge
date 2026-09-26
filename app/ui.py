import sys
from typing import Optional
from multiprocessing.connection import Client
import time
from PyQt6.QtCore import Qt, QTimer, QPoint, QRectF, QThread, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QColor, QFont, QLinearGradient, QBrush, QPainterPath
from PyQt6.QtWidgets import QApplication, QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QFrame

class StatsClient:
    def __init__(self, address=("localhost", 6000), authkey=b"corepulse") -> None:
        self.address = address
        self.authkey = authkey
        self.conn = None
        self._connect()

    def _connect(self):
        try:
            self.conn = Client(address=self.address, authkey=self.authkey)
        except Exception:
            self.conn = None

    def fetch(self):
        if self.conn is None:
            self._connect()
            if self.conn is None:
                return {"cpu": {"percent": 0}, "mem": {"percent": 0, "used": 0, "total": 0}, "gpu": {"supported": False}, "net": {"up": 0, "down": 0}}
        try:
            self.conn.send("get")
            data = self.conn.recv()
            return data
        except Exception:
            try:
                if self.conn:
                    self.conn.close()
            except Exception:
                pass
            self.conn = None
            return {"cpu": {"percent": 0}, "mem": {"percent": 0, "used": 0, "total": 0}, "gpu": {"supported": False}, "net": {"up": 0, "down": 0}}

    def stop(self):
        try:
            if self.conn:
                self.conn.send("quit")
        except Exception:
            pass
        try:
            if self.conn:
                self.conn.close()
        except Exception:
            pass

class StatsWorker(QThread):
    data_ready = pyqtSignal(dict)
    def __init__(self, client: StatsClient, interval_ms: int = 1000):
        super().__init__()
        self.client = client
        self.interval_ms = interval_ms
        self._running = True
    def run(self):
        while self._running and not self.isInterruptionRequested():
            data = self.client.fetch()
            self.data_ready.emit(data)
            self.msleep(self.interval_ms)
    def stop(self):
        self._running = False
        self.requestInterruption()

class CircularGauge(QWidget):
    def __init__(self, title: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._value: float = 0.0
        self._title: str = title
        self._is_dark = False
        self.setMinimumSize(130, 130)
        self.accent_color = QColor(0, 120, 215)

    def setValue(self, value: float):
        if self._value != value:
            self._value = max(0.0, min(100.0, value))
            self.update()

    def setDarkMode(self, enabled: bool):
        self._is_dark = enabled
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.width()
        height = self.height()
        side = min(width, height) - 25
        rect = QRectF((width - side) / 2, (height - side) / 2, side, side)
        rail_color = QColor(255, 255, 255, 30) if self._is_dark else QColor(0, 0, 0, 35)
        bg_pen = QPen(rail_color, 8)
        bg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(bg_pen)
        painter.drawEllipse(rect)
        if self._value > 0:
            grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
            if self._is_dark:
                grad.setColorAt(0, QColor(0, 255, 200))
                grad.setColorAt(1, QColor(0, 180, 255))
            else:
                grad.setColorAt(0, QColor(0, 195, 255))
                grad.setColorAt(1, self.accent_color)
            val_pen = QPen(QBrush(grad), 10)
            val_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(val_pen)
            start_angle = 270 * 16
            span_angle = -int(self._value * 3.6 * 16)
            painter.drawArc(rect, start_angle, span_angle)
        text_color = QColor(230, 230, 230) if self._is_dark else QColor(30, 30, 30)
        painter.setPen(text_color)
        painter.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{int(self._value)}%")
        painter.setFont(QFont("Microsoft YaHei UI", 9))
        label_color = QColor(180, 180, 180) if self._is_dark else QColor(80, 80, 80)
        painter.setPen(label_color)
        label_rect = rect.adjusted(0, 35, 0, 35)
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, self._title)

class GlassBackground(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_dark = False
        self.bg_color_light = QColor(255, 255, 255, 160)
        self.bg_color_dark = QColor(30, 30, 30, 180)

    def setDarkMode(self, enabled: bool):
        self._is_dark = enabled
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 18, 18)
        bg = self.bg_color_dark if self._is_dark else self.bg_color_light
        painter.fillPath(path, bg)
        border_color = QColor(255, 255, 255, 40) if self._is_dark else QColor(255, 255, 255, 200)
        painter.setPen(QPen(border_color, 1.5))
        painter.drawPath(path)

class CorePulseApp(QWidget):
    def __init__(self, address=("localhost", 6000), authkey=b"corepulse"):
        super().__init__()
        self.client = StatsClient(address=address, authkey=authkey)
        self.worker = StatsWorker(self.client, 1000)
        self._last_data = {"cpu": {"percent": 0}, "mem": {"percent": 0, "used": 0, "total": 0}, "gpu": {"supported": False}, "net": {"up": 0, "down": 0}}
        self._drag_pos = QPoint()
        self._is_dark_mode = False
        self._quitting = False
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(620, 240)
        self.bg = GlassBackground(self)
        self.bg.setGeometry(self.rect())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 15)
        top_bar = QHBoxLayout()
        self.net_lbl = QLabel("↑ 0 B/s  |  ↓ 0 B/s")
        self.net_lbl.setStyleSheet("color: #777; font-size: 11px; font-family: 'Segoe UI';")
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(26, 26)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #999; border-radius: 13px; font-weight: bold; }
            QPushButton:hover { background: #fb4d4d; color: white; }
        """)
        self.close_btn.clicked.connect(self.quit_hard)
        top_bar.addWidget(self.net_lbl)
        top_bar.addStretch()
        top_bar.addWidget(self.close_btn)
        layout.addLayout(top_bar)
        gauges_box = QHBoxLayout()
        self.cpu_g = CircularGauge("CPU")
        self.mem_g = CircularGauge("内存")
        self.gpu_g = CircularGauge("GPU")
        self.vram_g = CircularGauge("显存")
        self.gauges = [self.cpu_g, self.mem_g, self.gpu_g, self.vram_g]
        for g in self.gauges:
            gauges_box.addWidget(g)
        layout.addLayout(gauges_box)
        footer = QHBoxLayout()
        self.info_lbl = QLabel("Initializing...")
        self.info_lbl.setStyleSheet("color: #777; font-size: 11px; font-family: 'Segoe UI';")
        self.dark_btn = QPushButton("☾")
        self.dark_btn.setFixedSize(28, 28)
        self.dark_btn.setToolTip("切换黑暗模式")
        self.dark_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dark_btn_style = """
            QPushButton { background: rgba(0,0,0,0.06); border-radius: 14px; color: #666; font-size: 14px; border: none; }
            QPushButton:hover { background: rgba(0,0,0,0.12); }
        """
        self.dark_btn_style_dark = """
            QPushButton { background: rgba(255,255,255,0.1); border-radius: 14px; color: #aaa; font-size: 14px; border: none; }
            QPushButton:hover { background: rgba(255,255,255,0.2); }
        """
        self.dark_btn.setStyleSheet(self.dark_btn_style)
        self.dark_btn.clicked.connect(self.toggle_dark_mode)
        self.snap_btn = QPushButton("↘")
        self.snap_btn.setFixedSize(28, 28)
        self.snap_btn.setToolTip("靠齐右下角")
        self.snap_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.snap_btn_style = """
            QPushButton { background: rgba(0,0,0,0.06); border-radius: 14px; color: #666; font-size: 14px; border: none; }
            QPushButton:hover { background: rgba(0,0,0,0.12); }
        """
        self.snap_btn_style_dark = """
            QPushButton { background: rgba(255,255,255,0.1); border-radius: 14px; color: #aaa; font-size: 14px; border: none; }
            QPushButton:hover { background: rgba(255,255,255,0.2); }
        """
        self.snap_btn.setStyleSheet(self.snap_btn_style)
        self.snap_btn.clicked.connect(self.snap_to_corner)
        footer.addWidget(self.info_lbl)
        footer.addStretch()
        footer.addWidget(self.dark_btn)
        footer.addSpacing(5)
        footer.addWidget(self.snap_btn)
        layout.addLayout(footer)
        self.worker.data_ready.connect(self.refresh_ui_data)
        self.worker.start()
        self.snap_to_corner()
        self.refresh_ui_data(self._last_data)

    def toggle_dark_mode(self):
        self._is_dark_mode = not self._is_dark_mode
        self.bg.setDarkMode(self._is_dark_mode)
        for g in self.gauges:
            g.setDarkMode(self._is_dark_mode)
        if self._is_dark_mode:
            self.dark_btn.setText("☼")
            self.dark_btn.setStyleSheet(self.dark_btn_style_dark)
            self.snap_btn.setStyleSheet(self.snap_btn_style_dark)
            self.net_lbl.setStyleSheet("color: #aaa; font-size: 11px; font-family: 'Segoe UI';")
            self.info_lbl.setStyleSheet("color: #aaa; font-size: 11px; font-family: 'Segoe UI';")
        else:
            self.dark_btn.setText("☾")
            self.dark_btn.setStyleSheet(self.dark_btn_style)
            self.snap_btn.setStyleSheet(self.snap_btn_style)
            self.net_lbl.setStyleSheet("color: #777; font-size: 11px; font-family: 'Segoe UI';")
            self.info_lbl.setStyleSheet("color: #777; font-size: 11px; font-family: 'Segoe UI';")
        self.refresh_ui_data(self._last_data)

    def refresh_ui_data(self, data: dict):
        self._last_data = data
        c = data["cpu"]
        m = data["mem"]
        g = data["gpu"]
        n = data["net"]
        self.cpu_g.setValue(c.get("percent", 0))
        self.mem_g.setValue(m.get("percent", 0))
        def format_speed(speed):
            if speed < 1024:
                return f"{speed:.0f} B/s"
            if speed < 1024*1024:
                return f"{speed/1024:.1f} KB/s"
            return f"{speed/(1024*1024):.1f} MB/s"
        self.net_lbl.setText(f"↓ {format_speed(n.get('down', 0))}  |  ↑ {format_speed(n.get('up', 0))}")
        msg = f"RAM: {m.get('used', 0):.1f}/{m.get('total', 0):.1f} GB"
        if g.get("supported", False):
            self.gpu_g.setValue(g.get("percent", 0))
            if g.get("memory_supported", False):
                self.vram_g.setValue(g.get("mem_percent", 0))
                msg += f"  |  VRAM: {g.get('used', 0):.1f}/{g.get('total', 0):.1f} GB"
            else:
                self.vram_g.setValue(0)
            msg += f"  |  GPU: {g.get('name', 'Detected')}"
        else:
            self.gpu_g.setValue(0)
            self.vram_g.setValue(0)
            msg += "  |  GPU: Not Detected"
        self.info_lbl.setText(msg)

    def snap_to_corner(self):
        screen = self.screen().availableGeometry()
        self.move(
            screen.x() + screen.width() - self.width() - 20,
            screen.y() + screen.height() - self.height() - 20
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def closeEvent(self, event):
        self.quit_hard()
        event.ignore()

    def quit_hard(self):
        try:
            self.worker.stop()
            self.worker.wait(1000)
            self.client.stop()
        except Exception:
            pass
        try:
            QApplication.instance().quit()
        finally:
            sys.exit(0)

def run_app(address=("localhost", 6000), authkey=b"corepulse"):
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei UI", 9))
    window = CorePulseApp(address=address, authkey=authkey)
    window.show()
    sys.exit(app.exec())
