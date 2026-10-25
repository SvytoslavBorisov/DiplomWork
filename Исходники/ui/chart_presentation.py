"""Оформляет готовые научные серии без изменения измерений и расчётов."""

from copy import deepcopy

from PySide6.QtCore import Qt, QEvent, QObject, QPointF
from PySide6.QtGui import QFontMetrics, QFontMetricsF, QPainter, QColor, QPen, QPainterPath
from PySide6.QtWidgets import QComboBox, QFrame, QListView

from algorithms.search_methods import SearchMethod
from integration.comparison_analysis import METHOD_NAMES
from .fonts import header_font_family


METHOD_COLORS={'classical':'#2464FF','grover_fixed':'#934EFF','grover_bbht':'#00AB73'}


class ChartTitleCombo(QComboBox):
    def __init__(self,parent=None):
        super().__init__(parent)
        self._popup_open=False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        view=QListView(self);view.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.setView(view)
        self.currentIndexChanged.connect(lambda *_:self.updateGeometry())

    def sizeHint(self):
        size=super().sizeHint()
        size.setWidth(QFontMetrics(self.font()).horizontalAdvance(self.currentText())+28)
        return size

    def minimumSizeHint(self):
        size=super().minimumSizeHint();size.setWidth(80)
        return size

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(self.font());color=QColor('#2464FF' if self.underMouse() else '#101010');painter.setPen(color)
        metrics=QFontMetricsF(self.font());text=self.currentText()
        baseline=(self.height()-metrics.height())/2+metrics.ascent()
        painter.drawText(QPointF(0,baseline),text)
        x=metrics.horizontalAdvance(text)+5
        center=baseline+metrics.tightBoundingRect(text).center().y()
        direction=-1 if self._popup_open else 1
        path=QPainterPath(QPointF(x,center-2*direction));path.lineTo(x+6,center+2*direction);path.lineTo(x+12,center-2*direction)
        painter.setPen(QPen(color,2,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin));painter.drawPath(path)

    def enterEvent(self,event):
        super().enterEvent(event);self.update()

    def leaveEvent(self,event):
        super().leaveEvent(event);self.update()

    def hidePopup(self):
        super().hidePopup();self._popup_open=False;self.update()

    def showPopup(self):
        font=self.font();font.setBold(False);font.setPixelSize(14);self.view().setFont(font)
        self.view().setStyleSheet(f'QListView {{font-family:"{header_font_family()}";font-size:14px;font-weight:400;}}')
        width=max(QFontMetrics(self.view().font()).horizontalAdvance(self.itemText(i)) for i in range(self.count()))+48
        self.view().setMinimumWidth(width)
        self._popup_open=True;self.update()
        super().showPopup()
        self.view().window().setStyleSheet('QFrame {background:white;border:1px solid #DCE6F5;border-top-left-radius:0;border-top-right-radius:0;border-bottom-left-radius:8px;border-bottom-right-radius:8px;} QListView {border:0;padding:6px;} QListView::item {padding:9px 12px;}')


class ChartBackplate(QObject):
    """Рисует тень соседним слоем без перехвата композиции QtWebEngine."""

    def __init__(self,chart):
        super().__init__(chart)
        from .widgets import add_panel_shadow
        self.chart=chart;chart.setGraphicsEffect(None)
        self.surface=QFrame(chart.parentWidget())
        self.surface.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.surface.setStyleSheet('background:white;border:1px solid #E5EBF3;border-radius:14px;')
        add_panel_shadow(self.surface);chart.installEventFilter(self)

    def eventFilter(self,watched,event):
        if event.type() in (QEvent.Type.Move,QEvent.Type.Resize,QEvent.Type.Show):
            self.surface.setGeometry(self.chart.geometry());self.surface.show();self.surface.stackUnder(self.chart)
        elif event.type()==QEvent.Type.Hide:self.surface.hide()
        return False

def present_chart(spec):
    result=deepcopy(spec)
    layout=result['layout']
    family=header_font_family()
    layout.update(title=None,showlegend=False,dragmode=False,paper_bgcolor='#FFFFFF',plot_bgcolor='#FFFFFF',
                  font=dict(family=family,size=12,color='#526581'),margin=dict(l=72,r=20,t=15,b=54),
                  hovermode='closest',hoverlabel=dict(bgcolor='#FFFFFF',bordercolor='#DCE6F5',font=dict(family=family,size=12,color='#102742')))
    for axis in ('xaxis','yaxis'):
        layout[axis].update(fixedrange=True,gridcolor='#EDF1F8')
    for trace in result['data']:
        method=trace.get('legendgroup')
        if method not in METHOD_COLORS:
            method=next((m.value for m in SearchMethod if trace.get('name','').startswith(METHOD_NAMES[m])),None)
        if not method:continue
        trace['legendgroup']=method
        trace['showlegend']=False
        color=METHOD_COLORS[method]
        if 'line' in trace:trace['line'].update(color=color,width=2.8)
        marker=trace.setdefault('marker',{})
        marker['color']=color
        if trace['type']=='scatter':
            marker.update(size=13,symbol='circle',line=dict(width=1.7,color='#FFFFFF'),opacity=1)
            if result['options']['graph']=='dispersion' and trace.get('customdata'):
                marker.update(size=9,opacity=.65,line=dict(width=1,color='#FFFFFF'))
        if 'error_y' in trace:trace['error_y']['color']=color
        if trace['type']=='bar' and result['options']['graph']=='components':
            import re
            identities=[]
            for category in trace['x']:
                parameters={key:int(value) for key,value in re.findall(r'([nks])=(\d+)',category)}
                row=next((r for r in result['rows'] if r['method']==METHOD_NAMES[SearchMethod(method)] and all(r[key]==value for key,value in parameters.items())),None)
                identities.append(row['group'] if row else None)
            trace['customdata']=identities
        trace.pop('hovertemplate',None)
        trace['hoverinfo']='none'
        if trace['type']=='box':
            rgb=','.join(str(int(color[i:i+2],16)) for i in (1,3,5))
            trace.update(fillcolor=f'rgba({rgb},0.18)',line=dict(color=color,width=2),opacity=1,width=.35)
    return result
