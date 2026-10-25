"""Набирает формулы шрифтом интерфейса и рисует их прозрачными контурами Qt."""

from dataclasses import dataclass
from functools import lru_cache
import html
import re

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPainterPathStroker, QTransform, QPalette
from PySide6.QtWidgets import QLabel, QHeaderView, QStyle, QStyleOptionHeader, QStyleOptionComboBox, QStylePainter, QComboBox, QStyledItemDelegate, QApplication
from .fonts import header_font_family, math_font_family


@dataclass
class MathAsset:
    path: QPainterPath
    width: float
    ascent: float
    descent: float
    supported: bool = True

    @property
    def height(self):
        return self.ascent + self.descent


def _move(box, x, y):
    return QTransform.fromTranslate(x,y).map(box.path)


def _join(boxes):
    path=QPainterPath(); width=0
    for box in boxes:
        path.addPath(_move(box,width,0)); width+=box.width
    return MathAsset(path,width,max((b.ascent for b in boxes),default=0),max((b.descent for b in boxes),default=0))


_SYMBOLS={'Sigma':'Σ','sigma':'σ','psi':'ψ','alpha':'α','beta':'β','theta':'θ','pi':'π','Delta':'Δ','Omega':'Ω','sum':'∑','prod':'∏','infty':'∞','ast':'∗','cdot':'·','times':'×','le':'≤','leq':'≤','ge':'≥','geq':'≥','ne':'≠','neq':'≠','to':'→','rightarrow':'→','in':'∈','approx':'≈','ell':'ℓ','langle':'⟨','rangle':'⟩'}


class _Typesetter:
    def __init__(self,text):
        self.text=text; self.pos=0

    def glyph(self,text,size,italic=False):
        font=QFont(); font.setFamilies([header_font_family(), math_font_family()]); font.setPixelSize(max(1,round(size))); font.setItalic(italic)
        if text and all(char in set(''.join(_SYMBOLS.values())) for char in text):
            font.setFamily(math_font_family())
            font.setBold(True)
        metrics=QFontMetricsF(font); path=QPainterPath(); path.addText(QPointF(),font,text)
        return MathAsset(path,metrics.horizontalAdvance(text),metrics.ascent(),metrics.descent())

    def group(self,size,italic=False):
        if self.pos<len(self.text) and self.text[self.pos]=='{':
            self.pos+=1; box=self.sequence(size,italic,True)
            return box
        return self.atom(size,italic)

    def atom(self,size,italic=False):
        if self.pos>=len(self.text): return self.glyph('',size)
        char=self.text[self.pos]; self.pos+=1
        if char=='{': return self.sequence(size,italic,True)
        if char!='\\': return self.glyph(char,size,italic or char.isascii() and char.isalpha())
        match=re.match(r'[A-Za-z]+|.',self.text[self.pos:])
        if not match: return self.glyph('',size)
        command=match[0]; self.pos+=len(command)
        if command in ('left','right'): return self.atom(size,italic)
        if command in ('mathbfit','mathbf','mathit','mathrm','mathcal','text','operatorname'):
            return self.group(size,command in ('mathbfit','mathit'))
        if command=='frac':
            top=self.group(size*.82,italic); bottom=self.group(size*.82,italic); width=max(top.width,bottom.width)+size*.25
            axis=-size*.23; gap=size*.14; path=QPainterPath()
            path.addPath(_move(top,(width-top.width)/2,axis-gap-top.descent))
            path.addPath(_move(bottom,(width-bottom.width)/2,axis+gap+bottom.ascent))
            path.addRect(0,axis-size*.025,width,size*.05)
            return MathAsset(path,width,top.height+gap-axis,bottom.height+gap+axis)
        if command=='sqrt':
            body=self.group(size,italic); path=QPainterPath(); offset=size*.6
            path.addPath(_move(body,offset,0)); line=QPainterPath(QPointF(0,-size*.25))
            line.lineTo(size*.15,-size*.35); line.lineTo(size*.3,size*.05); line.lineTo(size*.53,-body.ascent-size*.06); line.lineTo(offset+body.width,-body.ascent-size*.06)
            stroker=QPainterPathStroker(); stroker.setWidth(size*.065); path.addPath(stroker.createStroke(line))
            return MathAsset(path,offset+body.width,body.ascent+size*.12,body.descent)
        if command in _SYMBOLS: return self.glyph(_SYMBOLS[command],size,False)
        if command in ('ln','log','exp','sin','cos','min','max'): return self.glyph(command,size,False)
        if command in (',',';',':',' ','quad','qquad','!'): return self.glyph(' ' if command!='!' else '',size)
        raise ValueError('Неизвестная математическая команда.')

    def sequence(self,size,italic=False,group=False):
        boxes=[]
        while self.pos<len(self.text):
            if self.text[self.pos]=='}':
                if not group: raise ValueError('Лишняя скобка.')
                self.pos+=1; break
            box=self.atom(size,italic); sub=sup=None
            while self.pos<len(self.text) and self.text[self.pos] in '_^':
                operator=self.text[self.pos]; self.pos+=1
                value=self.group(size*.66,italic)
                if operator=='_': sub=value
                else: sup=value
            if sub or sup:
                path=QPainterPath(box.path); width=box.width; ascent=box.ascent; descent=box.descent
                if sup:
                    y=-size*.53; path.addPath(_move(sup,width,y)); ascent=max(ascent,sup.ascent-y)
                if sub:
                    y=size*.29; path.addPath(_move(sub,width,y)); descent=max(descent,sub.descent+y)
                box=MathAsset(path,width+max(sub.width if sub else 0,sup.width if sup else 0),ascent,descent)
            boxes.append(box)
        return _join(boxes)


@lru_cache(maxsize=2048)
def formula_layout(expression: str, pixels: float=18, color: str='#102742', scale: float=1.0) -> MathAsset:
    try:
        return _Typesetter(expression.strip().strip('$')).sequence(pixels)
    except (ValueError,RecursionError):
        box=_Typesetter('').glyph('Формула недоступна',pixels); box.supported=False; return box


def draw_formula(painter: QPainter, expression: str, rect: QRectF, pixels: float=18, color: str='#102742', scale: float=1.0):
    asset=formula_layout(expression,pixels,color,scale)
    ratio=min(1.0,rect.width()/max(1,asset.width),rect.height()/max(1,asset.height))
    painter.save(); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate(rect.center().x()-asset.width*ratio/2,rect.center().y()+(asset.ascent-asset.descent)*ratio/2)
    painter.scale(ratio,ratio); painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor(color)); painter.drawPath(asset.path); painter.restore()


def inline_formula(expression: str, **kwargs) -> str:
    text=expression.strip('$')
    for command,symbol in _SYMBOLS.items(): text=text.replace('\\'+command,symbol)
    text=re.sub(r'\\(?:mathbfit|mathbf|mathit|mathrm|mathcal|text)\{([^{}]*)\}',r'\1',text)
    text=html.escape(text)
    text=re.sub(r'([_^])(?:\{([^{}]+)\}|([A-Za-z0-9∗]))',lambda m: '<'+('sup' if m[1]=='^' else 'sub')+'>'+ (m[2] or m[3])+'</'+('sup' if m[1]=='^' else 'sub')+'>',text)
    text=re.sub(r'[ΣσψαβθπΔΩ∑∏∞∗≤≥≠→∈≈ℓ⟨⟩]',lambda m: '<span style="font-family:STIXGeneral; font-weight:700;">'+m[0]+'</span>',text)
    return '<span>'+text+'</span>'


class MathLabel(QLabel):
    """Рисует формулу векторно и сохраняет исходную нотацию для экспорта."""

    def __init__(self, expression: str = "", pixels: int = 22, parent=None):
        super().__init__(parent)
        self.pixels = pixels
        self.expression = expression
        self.setAccessibleName("Математическое выражение")
        self.set_formula(expression)

    def set_formula(self, expression: str) -> None:
        self.expression = expression
        self._asset = formula_layout(expression, self.pixels)
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(round(self._asset.width) + 4, round(self._asset.height) + 6)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        draw_formula(painter, self.expression, QRectF(self.rect()).adjusted(2, 2, -2, -2),
                     self.pixels, color=self.palette().color(QPalette.ColorRole.WindowText).name())


class MathItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index) -> None:
        self.initStyleOption(option, index)
        expression = option.text
        option.text = ""
        QApplication.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, option, painter)
        draw_formula(painter, expression, QRectF(option.rect).adjusted(4, 2, -4, -2), 17, color=option.palette.color(QPalette.ColorRole.HighlightedText if option.state & QStyle.StateFlag.State_Selected else QPalette.ColorRole.Text).name())


class MathComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        for expression in ("n", "k"):
            formula_layout(expression, 17)
        self.setItemDelegate(MathItemDelegate(self))

    def paintEvent(self, event) -> None:
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        option.currentText = ""
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)
        draw_formula(painter, self.currentText(), QRectF(self.rect()).adjusted(5, 3, -24, -3), 17)


class MathHeaderView(QHeaderView):
    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        for expression in ("n", "k", "N", "s", "Q", "g", "L", "S", "|E|"):
            formula_layout(expression, 16)

    def paintSection(self, painter, rect, logicalIndex) -> None:
        text = str(self.model().headerData(logicalIndex, Qt.Orientation.Horizontal) or "")
        if text not in ("n", "k", "N", "s", "Q", "g", "L", "S", "|E|"):
            super().paintSection(painter, rect, logicalIndex)
            return
        option = QStyleOptionHeader()
        self.initStyleOptionForIndex(option,logicalIndex)
        option.rect = rect
        option.section = logicalIndex
        option.text = ""
        self.style().drawControl(QStyle.ControlElement.CE_Header, option, painter, self)
        draw_formula(painter, text, QRectF(rect).adjusted(3, 3, -3, -3), 16)
