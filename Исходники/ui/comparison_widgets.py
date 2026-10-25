"""Оформляет существующие записи сравнения без изменения экспериментальных данных."""

from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QColor,QPainter
from PySide6.QtWidgets import QTableWidgetItem,QStyledItemDelegate,QStyle,QToolButton
from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from pathlib import Path
from algorithms.search_methods import SearchMethod


def action_button(icon, tooltip):
    """Создаёт компактную кнопку панели сравнения с общей иконкой приложения."""
    button=QToolButton();button.setObjectName("resultActionButton");button.setFixedSize(26,28)
    button.setIcon(QIcon(str(Path(__file__).with_name("resources")/f"result_{icon}.svg")))
    button.setIconSize(QSize(17,17));button.setToolTip(tooltip);button.setAccessibleName(tooltip)
    return button

COLORS={SearchMethod.CLASSICAL:"#2464FF",SearchMethod.GROVER_FIXED:"#934EFF",SearchMethod.GROVER_BBHT:"#00AB73"}


class SortableItem(QTableWidgetItem):
    def __init__(self,text):
        super().__init__(text)
        self.sort_value=text.casefold();self.natural_order=0;self.use_natural_order=False

    def __lt__(self,other):
        if self.use_natural_order:return self.natural_order<other.natural_order
        return self.sort_value<other.sort_value


class ExperimentDelegate(QStyledItemDelegate):
    def paint(self,painter,option,index):
        column=index.column()
        if column not in (0,10,11):return super().paint(painter,option,index)
        self.initStyleOption(option,index);text=option.text;option.text=""
        self.parent().style().drawControl(QStyle.ControlElement.CE_ItemViewItem,option,painter,self.parent())
        painter.save();painter.setRenderHint(QPainter.RenderHint.Antialiasing);painter.setFont(option.font)
        rect=QRectF(option.rect).adjusted(12,0,-8,0)
        if column==0:
            color=index.data(Qt.ItemDataRole.UserRole+2) or "#2464FF"
            painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(color));painter.drawEllipse(rect.left(),rect.center().y()-5,10,10)
            rect.adjust(19,0,0,0);painter.setPen(QColor("#12213B"))
        elif column==11:
            text='Полная атака' if text=='Полная атака' else 'Поиск' if text in ('Поиск связующего блока','Поиск связывающего блока') else 'Построение'
            width=min(max(0,option.rect.width()-24),option.fontMetrics.horizontalAdvance(text)+20)
            badge=QRectF(option.rect.center().x()-width/2,rect.center().y()-11,width,22)
            painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor("#E5EEFF"));painter.drawRoundedRect(badge,11,11)
            text=option.fontMetrics.elidedText(text,Qt.TextElideMode.ElideRight,max(0,int(width)-16))
            painter.setPen(QColor("#2464DF"));painter.drawText(badge,Qt.AlignmentFlag.AlignCenter,text);painter.restore();return
        else:
            success=text in ("Завершено","Загружено")
            color="#009A61" if success else "#C53030" if "Ошибка" in text else "#A67B31"
            text="Успешно" if success else text
            width=min(rect.width(),option.fontMetrics.horizontalAdvance(text)+17)
            rect.setLeft(option.rect.center().x()-width/2);rect.setWidth(width)
            painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(color));painter.drawEllipse(rect.left(),rect.center().y()-4,8,8)
            rect.adjust(17,0,0,0);painter.setPen(QColor(color))
        painter.drawText(rect,Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,option.fontMetrics.elidedText(text,Qt.TextElideMode.ElideRight,int(rect.width())))
        painter.restore()
