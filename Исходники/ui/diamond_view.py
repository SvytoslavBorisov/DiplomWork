from __future__ import annotations

from collections import defaultdict, deque
import weakref

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPainterPathStroker, QPen, QShortcut, QKeySequence
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsView, QStyleOptionGraphicsItem, QWidget

from integration.result_adapter import DiamondGraph, GraphNode, build_diamond_graph, path_edge_ids, related_paths
from .fonts import header_font_family
from .graph_inspector import GraphInspector
from .math_renderer import draw_formula, formula_layout


def _pen(color: str, width: float) -> QPen:
    pen = QPen(QColor(color), width)
    pen.setCosmetic(True)
    return pen


class LevelCaption(QGraphicsItem):
    """Сохраняет читаемый размер подписи уровня при масштабировании графа."""

    def __init__(self,level,owner):
        super().__init__()
        self.level=level
        self._owner=weakref.ref(owner)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def boundingRect(self):
        return QRectF(-40,0,80,30)

    def text(self):
        return f"Уровень {self.level}"

    def paint(self,painter,option,widget=None):
        owner=self._owner()
        small=owner is not None and owner.viewport().width()<500
        font=QFont(header_font_family());font.setPixelSize(10 if small else 12)
        painter.setFont(font);painter.setPen(QColor("#8395B0"))
        painter.drawText(self.boundingRect(),Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                         f"Уровень\n{self.level}" if small else self.text())


class StateItem(QGraphicsItem):
    """Рисует и выбирает вершину целиком, включая обе подписи."""

    def __init__(self, node, owner):
        super().__init__()
        self.node = node
        self._owner = weakref.ref(owner)
        self.radius = 43 if node.kind == "root" else 39
        self.role = "normal"
        self.expression = owner._symbol(node.level, node.index, node.kind)
        self.math_ready = False
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setZValue(2)

    def boundingRect(self):
        r = self.radius + 11
        return QRectF(-r, -r, 2*r, 2*r)

    def shape(self):
        path = QPainterPath()
        path.addEllipse(QPointF(0, 0), self.radius, self.radius)
        return path

    def paint(self, painter, option, widget=None):
        r = self.radius
        lod = QStyleOptionGraphicsItem.levelOfDetailFromTransform(painter.worldTransform())
        root = self.node.kind == "root"
        selected = self.role == "selected"
        related = self.role in ("ancestor", "forward")
        color = "#145CF2" if root or selected or self.role == "forward" else "#38A5FF" if related else "#AEBED4" if self.role == "muted" else "#7C9AC5"
        if self.role == "verification": color = "#246BFA"
        elif self.role == "verified": color = "#45B998"
        elif self.role == "failed": color = "#D33E48"
        fill = "#E9F4FF" if selected else "#F3F9FF" if root or related else "#FFFFFF"
        if lod * 2*r >= 22:
            for spread in range(10, 0, -2):
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(43, 120, 244, 5 if root or selected else 2))
                painter.drawEllipse(QPointF(0, 4), r + spread, r + spread)
        painter.setPen(_pen(color, 2 if selected or root else 1.3))
        painter.setBrush(QColor(fill))
        painter.drawEllipse(QPointF(0, 0), r, r)
        if lod * 2*r < 24:
            return
        if self.math_ready:
            draw_formula(painter, self.expression, QRectF(-r+6, -r+7, 2*r-12, r+4), 28)
        elif self._owner() is not None and not self._owner()._math_timer.isActive():
            self._owner()._math_timer.start(0)
        if lod * 2*r >= 28:
            font = QFont("Consolas")
            pixels = max(15, round(7.5/lod))
            font.setPixelSize(pixels)
            painter.setFont(font)
            painter.setPen(QColor("#4C668F"))
            limit = max(4, int((2*r-8)/(pixels*.61)))
            value = self.node.state if len(self.node.state) <= limit else self.node.state[:limit-1] + "…"
            painter.drawText(QRectF(-r+4, 4, 2*r-8, max(23,pixels*1.5)), Qt.AlignmentFlag.AlignCenter, value)

    def mousePressEvent(self, event):
        self._owner().select_node(self.node.node_id)
        event.accept()


class MessageItem(StateItem):
    """Показывает сообщение тем же кругом и тенью, что и вершины структуры."""

    def __init__(self,value,label,owner,linking):
        super().__init__(GraphNode(f"message:{int(linking)}",value,-1,0,"message"),owner)
        self.expression=r"m_{link}" if linking else r"h_P"
        self.label=label
        self.linking=linking
        formula_layout(self.expression,28)
        self.math_ready=True
        self.setToolTip(f"{label}: {value}")

    def mousePressEvent(self,event):
        owner=self._owner()
        owner.inspector.present(self.label,self.expression,{"Блок сообщения" if self.linking else "Хэш-код":self.node.state})
        owner._popover_anchor=self.pos();owner._position_inspector();event.accept()


class TransitionItem(QGraphicsPathItem):
    def __init__(self, path, edge, owner):
        super().__init__(path)
        self.edge = edge
        self._owner = weakref.ref(owner)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)

    def shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(10)
        return stroker.createStroke(self.path())

    def boundingRect(self):
        return self.path().boundingRect().adjusted(-5, -5, 5, 5)

    def mousePressEvent(self, event):
        self._owner().select_edge((self.edge.source, self.edge.target))
        event.accept()


class DiamondView(QGraphicsView):
    verification_progress = Signal(int, int, int)
    verification_animation_finished = Signal(int)
    verification_restored = Signal(int)
    def __init__(self, parent: QWidget | None = None, *, message_mode=False) -> None:
        super().__init__(parent)
        self._message_mode=message_mode
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QColor("#FFFFFF"))
        self._verification_token = None
        self._verification_confirmed = set()
        self._verification_current = None
        self._verification_failed = None
        self._verification_marks = {}
        self._verification_glow = None
        self._verification_root_items = []
        self._verification_fade = QVariantAnimation(self)
        self._verification_fade.setStartValue(.12)
        self._verification_fade.setKeyValueAt(.5,.55)
        self._verification_fade.setEndValue(.18)
        self._verification_fade.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._verification_fade.valueChanged.connect(self._fade_verification_glow)
        self._verification_queue = deque()
        self._verification_computed = False
        self._verification_timer = QTimer(self)
        self._verification_timer.setSingleShot(True)
        self._verification_timer.timeout.connect(self._advance_verification)
        self._verification_final_timer = QTimer(self)
        self._verification_final_timer.setSingleShot(True)
        self._verification_final_timer.timeout.connect(self._complete_verification)
        self._verification_restore_timer = QTimer(self)
        self._verification_restore_timer.setSingleShot(True)
        self._verification_restore_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._verification_restore_timer.setInterval(2000)
        self._verification_restore_timer.timeout.connect(self._restore_verification)
        self._graph: DiamondGraph | None = None
        self._edge_items = {}
        self._node_items = {}
        self._positions = {}
        self._by_id = {}
        self._attack_edges = set()
        self._selected_nodes = set()
        self._ancestor_edges = set()
        self._forward_edges = set()
        self._selected_node_id = None
        self._selected_edge_key = None
        self._auto_fit = True
        self._empty_drag = False
        self._min_scale = .001
        self._math_timer = QTimer(self)
        self._math_timer.setSingleShot(True)
        self._math_timer.timeout.connect(self._warm_visible_math)
        self._search_timer = QTimer(self)
        self._search_timer.timeout.connect(self._pulse_search)
        self._path_timer = QTimer(self)
        self._path_timer.timeout.connect(self._advance_attack_animation)
        self._search_label = None
        self._search_visible = False
        self._pending_edges = []
        self._pending_messages = None
        self._animation_phase = 0
        self._attack_items = []
        self.inspector = GraphInspector(self.viewport())
        self.inspector.closed.connect(self.clear_selection)
        self._popover_anchor = QPointF()
        self._escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._escape_shortcut.activated.connect(self.clear_selection)
        self.horizontalScrollBar().valueChanged.connect(self._position_inspector)
        self.verticalScrollBar().valueChanged.connect(self._position_inspector)
        self.show_placeholder()

    def _reset(self):
        self.clear_verification()
        self._math_timer.stop()
        self.stop_search()
        self._path_timer.stop()
        self._pending_edges = []
        self._pending_messages = None
        self._attack_edges.clear()
        self.clear_selection()
        self.scene().clear()
        self._node_items.clear()
        self._edge_items.clear()
        self._positions.clear()
        self._attack_items.clear()
        self._by_id.clear()

    def _text(self, text, size, color):
        font = QFont(header_font_family())
        font.setPixelSize(size)
        item = self.scene().addSimpleText(text, font)
        item.setBrush(QColor(color))
        item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        return item

    def show_placeholder(self) -> None:
        self._reset()
        self._graph = None
        levels = [[QPointF(x, y) for y in rows] for x, rows in ((-130, (-65,-22,22,65)), (0,(-44,44)), (130,(0,))) ]
        for index in range(2):
            for n, start in enumerate(levels[index]):
                end = levels[index+1][n//2]
                path = QPainterPath(start)
                path.cubicTo(QPointF((start.x()+end.x())/2,start.y()),QPointF((start.x()+end.x())/2,end.y()),end)
                item = self.scene().addPath(path, _pen("#D5E7FC", 1.5))
                item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        for column in levels:
            for point in column:
                self.scene().addEllipse(point.x()-13,point.y()-13,26,26,_pen("#C8DFFB",1.3),QBrush(QColor("#F5FAFF")))
        title = self._text("Алмазная структура не загружена" if self._message_mode else "Алмазная структура не построена", 19, "#102742")
        title.setPos(-title.boundingRect().width()/2,110)
        note_font = QFont(header_font_family())
        note_font.setPixelSize(12)
        note_text=("Загрузите алмазную структуру, чтобы начать\nпоиск связывающего блока." if self._message_mode else
                   "Задайте параметры и нажмите\n«Построить алмазную структуру»")
        note = self.scene().addText(note_text, note_font)
        note.setDefaultTextColor(QColor("#71809C"))
        note.setTextWidth(420)
        option = note.document().defaultTextOption()
        option.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        note.document().setDefaultTextOption(option)
        note.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        note.setPos(-210,148)
        self.scene().setSceneRect(self.scene().itemsBoundingRect().adjusted(-15,-15,15,15))
        self.fit_to_view()

    def set_data(self, data: dict, *, preserve_view: bool = False) -> None:
        graph = build_diamond_graph(data)
        transform = self.transform()
        center = self.mapToScene(self.viewport().rect().center())
        if graph != self._graph or not preserve_view:
            self.set_graph(graph)
        if preserve_view:
            self._auto_fit = False
            self.setTransform(transform)
            self.centerOn(center)

    def set_graph(self, graph: DiamondGraph) -> None:
        self._reset()
        self._graph = graph
        levels = defaultdict(list)
        incoming = defaultdict(list)
        for node in graph.nodes:
            levels[node.level].append(node)
        for edge in graph.edges:
            incoming[edge.target].append(edge.source)
        self._by_id = {node.node_id:node for node in graph.nodes}
        leaves = []
        seen = set()
        parents = {edge.source for edge in graph.edges}
        forest_roots = sorted((node for node in graph.nodes if node.node_id not in parents),
                              key=lambda node:(-node.level,node.index))
        pending = [node.node_id for node in reversed(forest_roots)]
        while pending:
            node_id = pending.pop()
            if node_id in seen:
                continue
            seen.add(node_id)
            if incoming[node_id]:
                pending.extend(reversed(incoming[node_id]))
            elif self._by_id[node_id].level == 0:
                leaves.append(node_id)
        leaves.extend(n.node_id for n in levels[0] if n.node_id not in seen)
        spacing = 82.0
        x_gap = 280.0
        self._positions = {node_id:QPointF(0,index*spacing) for index,node_id in enumerate(leaves)}
        for level in range(1,graph.depth+1):
            for node in levels[level]:
                sources = incoming[node.node_id]
                y = sum(self._positions[source].y() for source in sources)/max(1,len(sources))
                self._positions[node.node_id] = QPointF(level*x_gap,y)
        total_height = max(82,(len(leaves)-1)*spacing)
        separator_pen = _pen("#E0EBFA",1)
        separator_pen.setStyle(Qt.PenStyle.DashLine)
        for level in range(graph.depth):
            line = self.scene().addLine((level+.5)*x_gap,-42,(level+.5)*x_gap,total_height+42,separator_pen)
            line.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            line.setZValue(-2)
        for level in range(graph.depth + 1):
            caption = LevelCaption(level,self)
            self.scene().addItem(caption)
            caption.setPos(level*x_gap,total_height+54)
        for edge in graph.edges:
            start,end = self._positions[edge.source],self._positions[edge.target]
            path = QPainterPath(start)
            middle = (start.x()+end.x())/2
            path.cubicTo(QPointF(middle,start.y()),QPointF(middle,end.y()),end)
            item = TransitionItem(path,edge,self)
            item.setPen(_pen("#89ABDA",1.4))
            self.scene().addItem(item)
            self._edge_items[edge.source,edge.target] = item
        for node in graph.nodes:
            item = StateItem(node,self)
            item.setPos(self._positions[node.node_id])
            self.scene().addItem(item)
            self._node_items[node.node_id] = item
        self.scene().setSceneRect(self.scene().itemsBoundingRect().adjusted(-12,-8,12,8))
        self.fit_to_view()

    @staticmethod
    def _symbol(level: int, index: int, kind: str) -> str:
        if kind == "root":
            return r"\mathbfit{h}^{\ast}"
        symbol = r"\mathbfit{h}"
        return symbol + (f"_{{{index}}}" if level==0 else f"_{{{index}}}^{{{level}}}")

    def _manual_selection(self, node_id):
        self._selected_node_id = node_id
        self._selected_edge_key = None
        self._selected_nodes,self._ancestor_edges,self._forward_edges = related_paths(self._graph,node_id)
        self._refresh_styles()

    def select_node(self, node_id: str) -> None:
        if self._graph is None or node_id not in self._by_id:
            return
        self._manual_selection(node_id)
        node = self._by_id[node_id]
        incoming = [edge for edge in self._graph.edges if edge.target==node_id]
        fields = {"Хэш-код":node.state,"Уровень":str(node.level),"Тип вершины":{"leaf":"Начальная вершина","root":"Корневая вершина","state":"Промежуточная вершина"}[node.kind]}
        if self._graph.sigma_bits and node.sigma is not None:
            fields["Контрольная сумма"] = f"0x{node.sigma:x}"
        if incoming:
            counters = {edge.counter_N for edge in incoming}
            if len(counters)==1 and None not in counters:
                fields["N входящего перехода"] = str(next(iter(counters)))
        self.inspector.present("Информация о вершине",self._symbol(node.level,node.index,node.kind),fields)
        self.inspector.rows["N входящего перехода"].setToolTip("Значение N перед обработкой входящего блока; на каждом следующем уровне оно увеличивается на 512 бит.")
        self._popover_anchor = self._positions[node_id]
        self._position_inspector()

    def select_edge(self, key: tuple[str,str]) -> None:
        if key not in self._edge_items:
            return
        edge = self._edge_items[key].edge
        self._manual_selection(edge.source)
        self._selected_edge_key = key
        source,target = self._by_id[edge.source],self._by_id[edge.target]
        fields = {"Исходное состояние":source.state,"Конечное состояние":target.state,"Уровень":str(edge.level),"Блок сообщения":edge.block}
        if edge.counter_N is not None:
            fields["N перед обработкой блока"] = str(edge.counter_N)
        if self._graph.sigma_bits and source.sigma is not None and target.sigma is not None:
            fields["Изменение Σₛ"] = f"0x{source.sigma:x} → 0x{target.sigma:x}"
        self.inspector.present("Информация о переходе",r"G_n(h,m,N)",fields)
        self._popover_anchor = (self._positions[edge.source]+self._positions[edge.target])/2
        self._position_inspector()

    def clear_selection(self) -> None:
        self.inspector.hide()
        self._selected_node_id = None
        self._selected_edge_key = None
        self._selected_nodes = set()
        self._ancestor_edges = set()
        self._forward_edges = set()
        self._refresh_styles()

    def _refresh_styles(self):
        manual = self._selected_node_id is not None
        verified_nodes = {node for key in self._verification_confirmed for node in key}
        for node_id,item in self._node_items.items():
            role = "normal"
            if manual:
                role = "selected" if node_id==self._selected_node_id else "forward" if any(target==node_id for _,target in self._forward_edges) else "ancestor" if node_id in self._selected_nodes else "muted"
            if self._verification_token is not None:
                if self._verification_failed and node_id in self._verification_failed:
                    role = "failed"
                elif self._verification_current and node_id in self._verification_current:
                    role = "verification"
                elif node_id in verified_nodes:
                    role = "verified"
            if item.role!=role:
                item.role = role
                item.update()
        for key,item in self._edge_items.items():
            color,width = ("#2563EB",2.5) if key in self._attack_edges else ("#DCE5F1",1.1) if self._attack_edges else ("#89ABDA",1.4)
            if manual:
                color,width = ("#38A5FF",2.3) if key in self._ancestor_edges else ("#145CF2",2.7) if key in self._forward_edges else ("#DCE5F1",1.0)
            if self._verification_token is not None:
                color,width = ("#D33E48",3.2) if key==self._verification_failed else ("#246BFA",3.3) if key==self._verification_current else ("#80B8EF",2.0) if key in self._verification_confirmed else ("#AFC4DE",1.3)
            item.setPen(_pen(color,width))

    def set_partial_data(self, data):
        automatic = self._auto_fit
        transform = self.transform()
        center = self.mapToScene(self.viewport().rect().center())
        self.set_data(data)
        if not automatic:
            self._auto_fit = False
            self.setTransform(transform)
            self.centerOn(center)

    def finish_attack_animation(self):
        self._path_timer.stop()
        while self._pending_messages is not None:
            self._advance_attack_animation()

    def mark_messages_verified(self,failed=False):
        for item in self._attack_items:
            if isinstance(item,MessageItem):
                item.role="failed" if failed else "verified"
                item.update()

    def begin_verification(self, token):
        self.clear_verification()
        self._verification_token = token
        self._verification_computed = False
        self._verification_keys = {}
        for edge in self._graph.edges if self._graph else ():
            pair = self._by_id[edge.target].index
            side = "left" if (edge.level,pair,"left") not in self._verification_keys else "right"
            self._verification_keys[edge.level,pair,side] = (edge.source,edge.target)
        self._refresh_styles()

    def _verification_key(self, event):
        return self._verification_keys.get((event["level"],event["pair"],event["side"]))

    def enqueue_verification(self, token, events):
        if token!=self._verification_token: return
        self._verification_queue.extend(events)
        if not self._verification_timer.isActive() and not self._verification_final_timer.isActive():
            self._advance_verification()

    def verification_computed(self, token):
        if token!=self._verification_token: return
        self._verification_computed = True
        if not self._verification_timer.isActive(): self._advance_verification()

    def _mark_verified(self, key):
        if key in self._verification_confirmed: return
        self._verification_confirmed.add(key)
        point = self._edge_items[key].path().pointAtPercent(.82)
        circle = self.scene().addEllipse(point.x()-7,point.y()-7,14,14,_pen("#FFFFFF",1),QBrush(QColor("#12A774")))
        mark = self._text("✓",11,"#FFFFFF")
        mark.setPos(point.x()-mark.boundingRect().width()/2,point.y()-mark.boundingRect().height()/2)
        for item in (circle,mark):
            item.setZValue(5); item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._verification_marks[key] = (circle,mark)

    def _fade_verification_glow(self, value):
        if self._verification_glow is not None:
            self._verification_glow.setOpacity(float(value))

    def _remove_verification_glow(self):
        self._verification_fade.stop()
        if self._verification_glow is not None:
            self.scene().removeItem(self._verification_glow)
            self._verification_glow = None

    def _advance_verification(self):
        if self._verification_token is None: return
        if self._verification_current:
            self._mark_verified(self._verification_current)
            self._verification_current = None
        self._remove_verification_glow()
        if self._verification_queue:
            batch = min(max(32,(len(self._edge_items)+79)//80),len(self._verification_queue)) if len(self._edge_items)>64 else 1
            event = None
            for _ in range(batch):
                event = self._verification_queue.popleft()
                key = self._verification_key(event)
                if key:
                    if batch>1: self._mark_verified(key)
                    self._verification_current = key
            if self._verification_current:
                glow = self.scene().addPath(self._edge_items[self._verification_current].path(),_pen("#A9D1FF",8))
                glow.setOpacity(.4); glow.setZValue(-.5); glow.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                self._verification_glow = glow
                self._verification_fade.setDuration(160 if batch==1 else 45)
                self._verification_fade.start()
            self.verification_progress.emit(self._verification_token,event["completed"],event["total"])
            self._verification_timer.start(160 if batch==1 else 45)
        elif self._verification_computed:
            self._verification_final_timer.start(180)
        self._refresh_styles()

    def _complete_verification(self):
        if self._verification_token is None: return
        self._verification_current = None
        self._refresh_styles()
        for node_id,item in self._node_items.items():
            if item.node.kind=="root":
                point=item.pos()+QPointF(30,-30)
                circle=self.scene().addEllipse(point.x()-10,point.y()-10,20,20,_pen("#FFFFFF",1.5),QBrush(QColor("#12A774")))
                mark=self._text("✓",14,"#FFFFFF")
                mark.setPos(point.x()-mark.boundingRect().width()/2,point.y()-mark.boundingRect().height()/2)
                for badge in (circle,mark):
                    badge.setZValue(6); badge.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                self._verification_root_items.extend((circle,mark))
        token = self._verification_token
        self.verification_animation_finished.emit(token)
        if self._verification_token == token:
            self._verification_restore_timer.start()

    def fail_verification(self, token, outcome):
        if token!=self._verification_token: return
        self._verification_timer.stop(); self._verification_final_timer.stop(); self._verification_restore_timer.stop()
        self._verification_queue.clear(); self._remove_verification_glow(); self._verification_current = None
        if outcome.get("level") is not None:
            self._verification_failed = self._verification_key(outcome)
        self._refresh_styles()

    def clear_verification(self):
        self._verification_timer.stop(); self._verification_final_timer.stop(); self._verification_restore_timer.stop()
        self._verification_queue.clear()
        self._remove_verification_glow()
        for items in self._verification_marks.values():
            for item in items: self.scene().removeItem(item)
        self._verification_marks.clear(); self._verification_confirmed.clear()
        for item in self._verification_root_items: self.scene().removeItem(item)
        self._verification_root_items.clear()
        self._verification_current = self._verification_failed = None
        self._verification_token = None
        for item in self._attack_items if hasattr(self,"_attack_items") else ():
            if isinstance(item,MessageItem):
                item.role="normal";item.update()
        if hasattr(self,"_node_items"): self._refresh_styles()

    def _restore_verification(self):
        token = self._verification_token
        self.clear_verification()
        if token is not None: self.verification_restored.emit(token)

    def _position_inspector(self, *_):
        if not self.inspector.isVisible():
            return
        point = self.mapFromScene(self._popover_anchor)
        radius = 42*self.transform().m11()+12
        width,height = self.inspector.width(),self.inspector.height()
        x = point.x()+radius
        if x+width>self.viewport().width()-8:
            x = point.x()-radius-width
        y = point.y()-50
        if y+height>self.viewport().height()-8:
            y = point.y()-height+50
        self.inspector.move(round(max(8,min(x,self.viewport().width()-width-8))),round(max(8,min(y,self.viewport().height()-height-8))))

    def mousePressEvent(self,event):
        item = self.itemAt(event.position().toPoint())
        self._empty_drag = event.button()==Qt.MouseButton.LeftButton and not isinstance(item,(StateItem,TransitionItem))
        if self._empty_drag:
            self.clear_selection()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._empty_drag and event.buttons() & Qt.MouseButton.LeftButton:
            self._auto_fit = False
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._empty_drag = False
        super().mouseReleaseEvent(event)

    def start_search(self) -> None:
        self.stop_search()
        if self._graph is None:
            return
        self._search_label = self._text("Поиск связывающего блока…",16,"#2878F8")
        rect = self.scene().sceneRect()
        self._search_label.setPos(rect.center().x()-self._search_label.boundingRect().width()/2,rect.top()-36)
        self._search_visible = True
        self._search_timer.start(450)
        if self._auto_fit:
            self.fit_to_view()

    def _pulse_search(self):
        if self._search_label is not None:
            self._search_visible = not self._search_visible
            self._search_label.setOpacity(1 if self._search_visible else .35)

    def stop_search(self) -> None:
        self._search_timer.stop()
        if self._search_label is not None:
            self.scene().removeItem(self._search_label)
            self._search_label = None

    def highlight_path(self, leaf_state: str) -> None:
        if self._graph is not None:
            self._attack_edges = path_edge_ids(self._graph,leaf_state)
            self._refresh_styles()

    def animate_attack_path(self, leaf_state: str, prefix_state: str, linking_block: str) -> None:
        self.stop_search()
        self._path_timer.stop()
        if self._graph is None:
            return
        self._attack_edges = set()
        self._pending_edges = sorted(path_edge_ids(self._graph,leaf_state),key=lambda key:self._by_id[key[0]].level)
        self._pending_messages = (prefix_state,linking_block,leaf_state)
        self._animation_phase = 0
        self._refresh_styles()
        self._advance_attack_animation()
        self._path_timer.start(350)

    def _advance_attack_animation(self):
        if self._pending_messages is None:
            self._path_timer.stop()
            return
        prefix,block,leaf = self._pending_messages
        if self._animation_phase==0:
            self._add_attack_message("Начальное сообщение",prefix,leaf,-400)
            self._animation_phase = 1
        elif self._animation_phase==1:
            self._add_attack_message("Связывающий блок",block,leaf,-200)
            self._connect_attack_messages(leaf)
            self._animation_phase = 2
        else:
            self._reveal_next_edge()

    def _reveal_next_edge(self):
        if self._pending_edges:
            self._attack_edges.add(self._pending_edges.pop(0))
            self._refresh_styles()
        else:
            self._path_timer.stop()
            self._pending_messages = None

    def _leaf_point(self,leaf_state):
        leaf = next((n for n in self._by_id.values() if n.kind=="leaf" and n.state==leaf_state),None)
        return None if leaf is None else self._positions[leaf.node_id]

    def _add_attack_message(self,label,value,leaf_state,offset):
        target = self._leaf_point(leaf_state)
        if target is None:
            return
        x,y = target.x()+offset,target.y()
        circle=MessageItem(value,label,self,offset==-200)
        circle.setPos(x,y)
        self.scene().addItem(circle)
        title=self._text(label,13,"#526581")
        title.setPos(x-title.boundingRect().width()/2,y-65)
        self._attack_items.extend((circle,title))
        self._fit_attack_bounds()

    def show_attack_messages(self,prefix_state,linking_block,leaf_state):
        self._add_attack_message("Начальное сообщение",prefix_state,leaf_state,-400)
        self._add_attack_message("Связывающий блок",linking_block,leaf_state,-200)
        self._connect_attack_messages(leaf_state)

    def _connect_attack_messages(self,leaf_state):
        point = self._leaf_point(leaf_state)
        if point is None:
            return
        for left,right in ((-361,-239),(-161,-39)):
            self._attack_items.append(self.scene().addLine(point.x()+left,point.y(),point.x()+right,point.y(),_pen("#89ABDA",1.4)))
        self._fit_attack_bounds()

    def _fit_attack_bounds(self):
        self.scene().setSceneRect(self.scene().itemsBoundingRect().adjusted(-12,-8,12,8))
        if self._auto_fit:
            self.fit_to_view()

    def _zoom(self,factor,anchor=None):
        current = self.transform().m11()
        factor = max(self._min_scale,min(4.0,current*factor))/current
        if anchor is None:
            anchor = self.viewport().rect().center()
        before = self.mapToScene(anchor)
        new_scale = current*factor
        margin = max(self.viewport().width(),self.viewport().height())/new_scale
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setSceneRect(self.scene().itemsBoundingRect().adjusted(-margin,-margin,margin,margin))
        self.scale(factor,factor)
        center = self.viewport().rect().center()
        self.centerOn(before+QPointF((center.x()-anchor.x())/new_scale,(center.y()-anchor.y())/new_scale))
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._warm_visible_math()
        self._auto_fit = False
        self._position_inspector()

    def zoom_in(self):
        self._zoom(1.18)

    def zoom_out(self):
        self._zoom(1/1.18)

    def _warm_visible_math(self):
        if self._graph is None:
            return
        lod = self.transform().m11()
        for item in self.items(self.viewport().rect()):
            if isinstance(item, StateItem) and not item.math_ready and lod*2*item.radius>=24:
                formula_layout(item.expression,28)
                item.math_ready = True
                item.update()

    def fit_to_view(self):
        self.setSceneRect(self.scene().sceneRect())
        bounds = self.scene().itemsBoundingRect()
        if not bounds.isEmpty():
            self.fitInView(bounds.adjusted(-8,-8,8,8),Qt.AspectRatioMode.KeepAspectRatio)
            if self._graph is not None:
                self.fitInView(bounds.adjusted(-8,-8,8,30/max(.001,self.transform().m11())),Qt.AspectRatioMode.KeepAspectRatio)
            if self._graph is None and self.transform().m11()>1:
                self.resetTransform()
                self.centerOn(bounds.center())
            self._min_scale = max(.0005,min(.04,self.transform().m11()/2))
        self._auto_fit = True
        self._warm_visible_math()
        self._position_inspector()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self._auto_fit:
            self.fit_to_view()
        if self.inspector.isVisible():
            self.inspector.fit_to_viewport()
            self._position_inspector()

    def wheelEvent(self,event):
        self._zoom(1.15 if event.angleDelta().y()>0 else 1/1.15,event.position().toPoint())
        event.accept()
