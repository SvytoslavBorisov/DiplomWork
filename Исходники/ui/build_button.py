"""Рисует стрелку построения вместе с надписью одним шрифтом."""

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainter,QFontMetricsF,QColor
from PySide6.QtWidgets import QPushButton,QStyle,QStyleOptionButton


class BuildButton(QPushButton):
    def paintEvent(self,event):
        option=QStyleOptionButton();self.initStyleOption(option);option.text=''
        painter=QPainter(self);self.style().drawControl(QStyle.ControlElement.CE_PushButton,option,painter,self)
        painter.setFont(self.font());painter.setPen(QColor('white' if self.isEnabled() else '#DCE9FF'))
        metrics=QFontMetricsF(self.font());text=self.text();arrow='›'
        gap=12;width=metrics.horizontalAdvance(text)+gap+metrics.horizontalAdvance(arrow)
        x=(self.width()-width)/2;baseline=self.height()/2-metrics.tightBoundingRect(text).center().y()
        painter.drawText(QPointF(x,baseline),text)
        painter.drawText(QPointF(x+metrics.horizontalAdvance(text)+gap,self.height()/2-metrics.tightBoundingRect(arrow).center().y()),arrow)
