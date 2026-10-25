"""Показывает локальный интерактивный Plotly с резервным научным отображением Qt."""

import json
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal, Slot, Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget, QSizePolicy, QProgressBar


class ChartBridge(QObject):
    selected = Signal(str)
    rendered = Signal()
    failed = Signal(str)
    point_clicked = Signal(str)

    @Slot(str)
    def select(self, identity):
        self.selected.emit(identity)

    @Slot()
    def ready(self):
        self.rendered.emit()

    @Slot(str)
    def error(self, message):
        self.failed.emit(message)

    @Slot(str)
    def point(self, payload):
        self.point_clicked.emit(payload)


class ScientificChart(QWidget):
    selected = Signal(str)
    rendered = Signal()
    point_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(0, 140)
        self.spec = None
        self.ready = False
        self.web = None
        self.error = None
        self._closed = False
        self._fallback = None
        self._selection = None
        self._first_render=False
        self._first_show=False
        self._box = QVBoxLayout(self);self._box.setContentsMargins(0,0,0,0)
        self.status = QLabel('Загрузка графика');self.status.setWordWrap(True);self.status.hide()
        self._loading=QWidget(self);self._loading.setStyleSheet('background:white;')
        loading=QVBoxLayout(self._loading);loading.addStretch()
        label=QLabel('Загрузка графика');label.setAlignment(Qt.AlignmentFlag.AlignCenter);loading.addWidget(label)
        progress=QProgressBar();progress.setRange(0,0);progress.setTextVisible(False);progress.setFixedSize(220,4)
        progress.setStyleSheet('QProgressBar{background:#EAF1FC;border:0;border-radius:2px} QProgressBar::chunk{background:#2464FF;border-radius:2px}')
        loading.addWidget(progress,0,Qt.AlignmentFlag.AlignHCenter);loading.addStretch()
        self._initialize()

    def resizeEvent(self,event):
        super().resizeEvent(event);self._loading.setGeometry(self.rect());self._loading.raise_()

    def _rendered(self):
        if self.isVisible():self._first_render=True;self._loading.hide()
        self.rendered.emit()

    def showEvent(self,event):
        super().showEvent(event)
        if not self._first_show:
            self._first_show=True;self._loading.setGeometry(self.rect());self._loading.show();self._loading.raise_()
            if self.ready and self.spec:self.set_spec(self.spec)
        if self.web is None and self.error is None:self._initialize()

    def _initialize(self):
        self._closed=False
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
            from PySide6.QtWebEngineCore import QWebEngineSettings
            from PySide6.QtWebChannel import QWebChannel
            script=Path(__file__).resolve().parents[1]/'plotly/package_data/plotly.min.js'
            if not script.is_file():
                import plotly
                script=Path(plotly.__file__).parent/'package_data/plotly.min.js'
            if not script.is_file():
                raise ImportError('Локальная библиотека plotly.min.js отсутствует.')
            self.web = QWebEngineView(self)
            self.web.setContextMenuPolicy(__import__('PySide6.QtCore',fromlist=['Qt']).Qt.ContextMenuPolicy.NoContextMenu)
            self.web.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
            self.web.setZoomFactor(1)
            self._channel = QWebChannel(self.web.page())
            self.bridge = ChartBridge(self)
            self.bridge.selected.connect(self.selected)
            self.bridge.rendered.connect(self._rendered)
            self.bridge.failed.connect(self._failed)
            self.bridge.point_clicked.connect(self.point_clicked)
            self._channel.registerObject('bridge',self.bridge)
            self.web.page().setWebChannel(self._channel)
            self.web.loadFinished.connect(self._loaded)
            self.web.page().renderProcessTerminated.connect(lambda *_:self._failed('Процесс отображения графика завершился.'))
            self._box.addWidget(self.web,1)
            self._loading.setGeometry(self.rect());self._loading.raise_()
            html = Path(__file__).with_name('resources').joinpath('scientific_chart.html').read_text(encoding='utf-8')
            html = html.replace('__PLOTLY_URL__', QUrl.fromLocalFile(str(script)).toString())
            from .fonts import header_font_family
            font=Path(__file__).with_name('resources')/'fonts/FredokaOneCyrillic-Regular.ttf'
            html=html.replace('__FONT_URL__',QUrl.fromLocalFile(str(font)).toString()).replace('__FONT_FAMILY__',header_font_family())
            self.web.setHtml(html,QUrl.fromLocalFile(str(script.parent)+'/'))
        except (ImportError, OSError) as exc:
            self._failed(str(exc))

    def _loaded(self, ok):
        if self._closed:return
        if not ok:
            self._failed('Не удалось загрузить локальный компонент графика.')
            return
        self.ready=True;self.status.hide()
        if self.spec:self.set_spec(self.spec)
        self.set_selection(self._selection)

    def _failed(self, message):
        if self._closed:return
        self.error=message
        self._loading.hide();self._box.insertWidget(0,self.status)
        self.status.setText('Интерактивный компонент недоступен: '+message+' Резервный график и экспорт доступны; установите зависимости из requirements.txt.')
        self.status.show()
        if self.web:self.web.hide()
        if self.spec:self._render_fallback()

    def _render_fallback(self):
        import io
        from PySide6.QtGui import QPixmap
        from tempfile import TemporaryDirectory
        from integration.scientific_charts import write_chart
        if self._fallback is None:
            self._fallback=QLabel();self._fallback.setScaledContents(True)
            self._fallback.setMinimumSize(0,0);self._fallback.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Ignored)
            self._box.addWidget(self._fallback,1)
        try:
            with TemporaryDirectory() as directory:
                path=Path(directory)/'chart.png';write_chart(path,self.spec,dpi=96)
                pixmap=QPixmap(str(path));self._fallback.setPixmap(pixmap)
        except Exception as exc:
            self.status.setText('График временно недоступен: '+str(exc))
        self.rendered.emit()

    def shutdown(self):
        self._closed=True;self.ready=False
        if self.web:
            self.web.stop();self.web.close();self.web.deleteLater();self.web=None

    def set_spec(self, spec):
        self.spec=spec
        if self.error:
            self._render_fallback();return
        if not self.ready:return
        payload=json.dumps({key:spec[key] for key in ('data','layout')},ensure_ascii=False,allow_nan=False)
        self.web.page().runJavaScript('window.setScientificPlot('+payload+');')

    def set_selection(self,target):
        self._selection=target
        if self.ready and self.web:
            self.web.page().runJavaScript('window.selectScientificPoint('+json.dumps(target)+');')

    def reset_zoom(self):
        return

    def zoom(self, factor):
        return

    def set_pan(self, enabled):
        return
