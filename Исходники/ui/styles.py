APP_STYLESHEET = """
* { font-family: "Fredoka One Cyrillic"; font-size: 13px; color: #172033; }
QMainWindow, QWidget#appRoot { background: #F5F7FA; }
QFrame#headerHost { background: transparent; border: 0; }
QFrame#header { background: #FFFFFF; border: 1px solid #EDF1F7; border-radius: 16px; }
QSvgWidget#headerLogo, QTabBar#headerTabs { background: transparent; border: 0; }
QTabBar#headerTabs::tab { background: transparent; border: 0; padding: 0; margin: 0; }
QFrame#card { background: #FFFFFF; border: 1px solid #E1E6EE; border-radius: 10px; }
QFrame#subCard { background: #F8FAFC; border: 1px solid #E6EAF0; border-radius: 8px; }
QFrame#parameterGroup { background: transparent; border: 0; border-radius: 0; }
QWidget#parameterContent, QWidget#resultContent { background: #FFFFFF; }
QFrame#metricRow { border: 0; border-bottom: 1px solid #EEF1F5; background: transparent; }
QFrame#kpiCard { background: #FFFFFF; border: 1px solid #DDE3EC; border-radius: 9px; }
QFrame#kpiCard[accent="quantum"] { background: #FFFFFF; border-color: #DDE3EC; }
QFrame#header QLabel#appTitle { color: #102742; background: transparent; border: 0; }
QLabel#subtitle { color: #667085; font-size: 13px; }
QLabel#sectionTitle { font-size: 17px; font-weight: 400; }
QLabel#groupTitle { color: #667085; font-size: 11px; font-weight: 400; }
QLabel#parameterHeading { color: #344054; font-size: 12px; font-weight: 400; }
QLabel#metricIcon { color: #98A2B3; font-size: 15px; min-width: 20px; }
QLabel#metricName { color: #475467; }
QLabel#metricValue { color: #2563EB; font-size: 18px; font-weight: 400; }
QLabel#metricSecondary { color: #667085; font-size: 14px; font-weight: 400; }
QLabel#hexValue { font-family: "Consolas"; color: #2563EB; font-size: 14px; font-weight: 400; }
QLabel#statusSuccess { color: #16A34A; font-weight: 400; }
QLabel#statusRunning { color: #2563EB; font-weight: 400; }
QLabel#statusError { color: #B42318; font-weight: 400; }
QLabel#badge { background: #F8FAFC; border: 1px solid #D8DEE8; border-radius: 7px; padding: 8px 11px; font-size: 12px; font-weight: 400; }
QLabel#badge[quantum="true"] { color: #5B4BC4; background: #F5F3FF; border-color: #DAD5F3; }
QLabel#infoBox { color: #475467; background: #F8FAFC; border: 1px solid #E1E6EE; border-radius: 7px; padding: 10px; }
QLabel#kpiTitle { color: #667085; font-size: 11px; font-weight: 400; }
QLabel#kpiValue { color: #2563EB; font-size: 26px; font-weight: 400; }
QLabel#kpiNote { color: #667085; font-size: 11px; }
QLabel#progressText { color: #64748B; font-size: 11px; }
QLabel#inspectorName { color: #64748B; font-size: 12px; }
QLabel#inspectorValue { color: #14213D; font-size: 12px; font-weight: 400; }
QWidget#inspectorBody { background: #FFFFFF; }
QWidget#chartInfo { background: #F8FAFC; border: 1px solid #E1E6EE; border-radius: 6px; }
QLabel#chartInfoText { color: #64748B; font-size: 11px; }
QLabel#infoIcon { color: #2563EB; font-size: 14px; }
QPushButton { min-height: 34px; padding: 2px 13px; border-radius: 6px; border: 1px solid #CBD5E1; background: #FFFFFF; }
QPushButton:hover { background: #F8FAFC; border-color: #98A2B3; }
QPushButton:disabled { color: #98A2B3; background: #EAECF0; }
QPushButton#primaryButton { min-height: 42px; color: white; background: #2563EB; border-color: #2563EB; font-weight: 400; }
QPushButton#primaryButton:hover { background: #1D4ED8; }
QPushButton#secondaryButton { min-height: 38px; }
QPushButton#compactLogButton { min-height: 20px; max-height: 20px; padding: 0 8px; font-size: 11px; }
QToolButton#toolButton { min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px; padding: 0; border: 1px solid #D8E0EC; border-radius: 6px; background: #FFFFFF; }
QToolButton#toolButton:hover { background: #EFF6FF; border-color: #2563EB; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit, QTableWidget {
    background: #FFFFFF; border: 1px solid #D8E0EC; border-radius: 6px; padding: 0 10px;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { min-height: 34px; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border: 1px solid #2563EB; }
QCheckBox { spacing: 7px; }
QCheckBox::indicator { width: 16px; height: 16px; }
QTabWidget::pane { border: 0; background: #F4F6F9; }
QTabBar { background: #FFFFFF; }
QTabBar::tab { min-height: 37px; padding: 0 10px; color: #475467; background: #FFFFFF; border: 0; border-bottom: 3px solid transparent; }
QTabBar::tab:selected { color: #2563EB; border-bottom-color: #2563EB; font-weight: 400; }
QTabBar::tab:hover:!selected { background: #F8FAFC; }
QSplitter::handle { background: transparent; width: 8px; height: 8px; }
QProgressBar { border: 0; border-radius: 5px; background: #EEF2F7; max-height: 10px; }
QProgressBar::chunk { background: #2563EB; }
QScrollBar:vertical { background: #F5F7FA; width: 8px; border: 0; }
QScrollBar::handle:vertical { background: #C3CDDA; border-radius: 4px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QHeaderView::section { background: #F8FAFC; color: #475467; padding: 7px; border: 0; border-bottom: 1px solid #DDE3EC; font-weight: 400; }
QTableWidget { gridline-color: #EEF1F5; selection-background-color: #EFF6FF; selection-color: #172033; }
QToolTip { color: #FFFFFF; background: #172033; border: 0; padding: 6px; }
"""

from pathlib import Path

_PARAMETER_RESOURCES = (Path(__file__).with_name("resources")).as_posix()
APP_STYLESHEET += """
QFrame#experimentParameterPanel { background: #FFFFFF; border: 1px solid #EDF2F9; border-radius: 16px; }
QFrame#experimentParameterPanel QLabel { color: #101B38; border: 0; background: transparent; }
QFrame#experimentParameterPanel QLabel#parameterPanelTitle { font-size: 17px; font-weight: 400; }
QFrame#experimentParameterPanel QScrollArea#parameterScroll,
QFrame#experimentParameterPanel QWidget#parameterContent { background: transparent; border: 0; }
QFrame#experimentParameterPanel QFrame#parameterSection { background: #F7FBFF; border: 1px solid #E3EDFC; border-radius: 13px; }
QFrame#experimentParameterPanel QLabel#parameterSectionTitle { font-size: 14px; font-weight: 400; }
QFrame#experimentParameterPanel QLabel#parameterLimitLabel { color: #71809C; }
QFrame#experimentParameterPanel QToolButton#parameterFileButton { background: #FCFDFF; border: 1px solid #D6E1F2; border-radius: 10px; padding: 0; }
QFrame#experimentParameterPanel QToolButton#parameterFileButton:hover { background: #EFF6FF; border-color: #9DC0FE; }
QFrame#experimentParameterPanel QToolButton#parameterHintButton { background: transparent; border: 0; padding: 0; }
QFrame#experimentParameterPanel QToolButton#parameterHintButton:hover { background: #E9F1FE; border-radius: 8px; }
QFrame#experimentParameterPanel QAbstractSpinBox#parameterInput { min-height: 40px; max-height: 40px; padding: 0 1px 0 10px; background: #FFFFFF; border: 1px solid #D6E1F2; border-radius: 10px; font-size: 14px; color: #101B38; }
QFrame#experimentParameterPanel QAbstractSpinBox#parameterInput:focus { border-color: #3B82F6; }
QFrame#experimentParameterPanel QAbstractSpinBox#parameterInput:disabled { color: #98A2B3; background: #F4F7FB; }
QFrame#experimentParameterPanel QAbstractSpinBox#parameterInput::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 18px; height: 14px; margin-top: 5px; margin-right: 5px; background: #F1F5FC; border: 0; border-radius: 4px; }
QFrame#experimentParameterPanel QAbstractSpinBox#parameterInput::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 18px; height: 14px; margin-bottom: 5px; margin-right: 5px; background: #F1F5FC; border: 0; border-radius: 4px; }
QFrame#experimentParameterPanel QAbstractSpinBox#parameterInput::up-button:hover,
QFrame#experimentParameterPanel QAbstractSpinBox#parameterInput::down-button:hover { background: #DEEAFF; }
QFrame#experimentParameterPanel QAbstractSpinBox#parameterInput::up-arrow { image: url($RESOURCE/parameter_up.svg); width: 13px; height: 13px; }
QFrame#experimentParameterPanel QAbstractSpinBox#parameterInput::down-arrow { image: url($RESOURCE/parameter_down.svg); width: 13px; height: 13px; }
QFrame#experimentParameterPanel QComboBox#parameterCombo { min-height: 0; background: #FFFFFF; border: 1px solid #7AACFF; border-radius: 10px; padding: 0; font-size: 12px; }
QFrame#experimentParameterPanel QComboBox#parameterCombo:focus { border-color: #2878F8; }
QFrame#experimentParameterPanel QComboBox#parameterCombo::drop-down { subcontrol-origin: border; subcontrol-position: right; width: 28px; border: 0; }
QFrame#experimentParameterPanel QComboBox#parameterCombo::down-arrow { image: url($RESOURCE/parameter_chevron.svg); width: 18px; height: 18px; }
QFrame#experimentParameterPanel QComboBox#parameterCombo:disabled { background: #F4F7FB; border-color: #DCE6F5; }
QFrame#experimentParameterPanel QScrollBar:vertical { background: transparent; width: 5px; }
QFrame#experimentParameterPanel QScrollBar::handle:vertical { background: #D8E3F4; border-radius: 2px; }
""".replace("$RESOURCE", _PARAMETER_RESOURCES)

APP_STYLESHEET += """
QFrame#diamondCanvasCard { background: #FFFFFF; border: 1px solid #E1EAF7; border-radius: 14px; }
QFrame#diamondCanvasCard QLabel#diamondCanvasTitle { font-size: 19px; color: #101B38; }
QFrame#diamondZoomGroup { background: #F8FBFF; border: 1px solid #DCE6F5; border-radius: 10px; }
QToolButton#diamondZoomButton { background: transparent; border: 0; border-radius: 9px; padding: 0; }
QToolButton#diamondZoomButton:hover { background: #EAF3FF; }
QFrame#diamondZoomDivider { background: #DCE6F5; border: 0; }
QPushButton#buildDiamondButton { min-height: 48px; padding: 0 16px; border: 0; border-radius: 11px; color: white; font-size: 14px; background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #397AFF,stop:1 #135CF5); }
QPushButton#buildDiamondButton:hover { background: #216AF8; }
QPushButton#buildDiamondButton:pressed { background: #1455DE; }
QPushButton#buildDiamondButton:disabled { color: #DCE9FF; background: #80A8EF; }
QFrame#graphInspector { background: white; border: 1px solid #DCE6F5; border-radius: 13px; }
QFrame#graphInspector QWidget#graphInspectorBody, QFrame#graphInspector QScrollArea { background: white; border: 0; }
QFrame#graphInspector QLabel { border: 0; background: transparent; color: #102742; font-size: 12px; }
QFrame#graphInspector QLabel#graphInspectorTitle { font-size: 14px; }
QFrame#graphInspector QLabel#graphInspectorCaption { color: #71809C; font-size: 11px; }
QFrame#graphInspector QLabel#graphInspectorHex { font-family: "Consolas"; color: #31578D; }
QFrame#graphInspector QToolButton { background: #F2F7FE; border: 0; border-radius: 5px; padding: 3px; color: #2878F8; }
QFrame#graphInspector QToolButton:hover { background: #DFEDFF; }
"""

APP_STYLESHEET += """
QFrame#structureResultPanel { background: white; border: 1px solid #DFE7F2; border-radius: 16px; }
QFrame#structureResultPanel QScrollArea, QFrame#structureResultPanel QWidget#resultContent { background: transparent; border: 0; }
QFrame#structureResultPanel QLabel { background: transparent; border: 0; color: #12213B; }
QFrame#structureResultPanel QLabel#resultPanelTitle { font-size: 19px; }
QFrame#resultMetricTile { background: #F5F8FD; border: 0; border-radius: 12px; }
QFrame#structureResultPanel QLabel#resultMetricValue { font-size: 28px; color: #0966FF; }
QFrame#structureResultPanel QLabel#resultMetricCaption { font-size: 13px; color: #71819B; }
QFrame#structureResultPanel QLabel#resultEmptyTitle { font-size: 17px; }
QFrame#resultStatusBanner { background: #EFFBF3; border: 0; border-radius: 11px; }
QFrame#resultStatusBanner QLabel { color: #009863; font-size: 13px; }
QFrame#resultStatusBanner QLabel#resultStatusSymbol { font-size: 20px; }
QFrame#resultStatusBanner[state="running"] { background: #F0F6FF; }
QFrame#resultStatusBanner[state="running"] QLabel { color: #2563EB; }
QFrame#resultStatusBanner[state="error"] { background: #FFF1F1; }
QFrame#resultStatusBanner[state="error"] QLabel { color: #C53030; }
QFrame#structureResultPanel QLabel#resultProgressCaption { font-size: 11px; color: #71819B; }
QFrame#structureResultPanel QLabel#resultVerificationNote { background: #F5F8FD; border-radius: 10px; color: #71819B; font-size: 12px; padding: 12px; }
QFrame#structureResultPanel QLabel#resultVerificationOutcome { color: #009863; font-size: 12px; }
QFrame#structureResultPanel QLabel#resultVerificationOutcome[state="failed"] { color: #C53030; }
QPushButton#verifyStructureButton { background: #2563EB; color: white; border: 0; border-radius: 11px; min-height: 46px; padding: 0 9px; font-size: 13px; }
QPushButton#verifyStructureButton:hover { background: #1D59DC; }
QPushButton#verifyStructureButton:pressed { background: #174BC3; }
QPushButton#verifyStructureButton:disabled { background: #8DB1F5; color: #F1F6FF; }
QPushButton#cancelVerificationButton { background: #FCFDFF; color: #607491; border: 1px solid #DFE7F2; min-height: 44px; border-radius: 10px; font-size: 12px; }
"""

APP_STYLESHEET += """
QFrame#experimentParameterPanel QLineEdit#herdingInput { min-height: 42px; padding: 0 10px; background: white; border: 1px solid #D6E1F2; border-radius: 10px; }
QFrame#experimentParameterPanel QLineEdit#herdingInput:focus { border-color: #3B82F6; }
"""

APP_STYLESHEET += """
QFrame#structureResultPanel QToolButton#resultDetailsToggle { border: 0; background: transparent; padding: 4px 0; color: #2563EB; font-size: 12px; }
QFrame#structureResultPanel QToolButton#resultDetailsToggle:hover { color: #174BC3; }
"""

APP_STYLESHEET += """
QFrame#structureResultPanel QFrame#resultPageSelector { border: 0; background: transparent; }
QFrame#structureResultPanel QToolButton#resultPageButton { border: 1px solid #D7E2F2; border-radius: 8px; background: #FCFDFF; padding: 0; }
QFrame#structureResultPanel QToolButton#resultPageButton:checked { background: #E9F2FF; border-color: #A9C8FF; }
QFrame#structureResultPanel QToolButton#resultPageButton:hover { background: #F0F6FF; border-color: #8EB8FD; }
QFrame#structureResultPanel QFrame#resultHeadingDivider { border: 0; background: #EAF0F8; }
QFrame#structureResultPanel QLabel#resultPageCaption { font-size: 10px; color: #71819B; }
QFrame#structureResultPanel QToolButton#resultActionButton { border: 1px solid #DFE7F2; background: #FCFDFF; border-radius: 6px; padding: 0; }
QFrame#structureResultPanel QToolButton#resultActionButton:hover { background: #EDF5FF; border-color: #A9C8FF; }
QFrame#structureResultPanel QTextEdit#resultLogEditor, QFrame#structureResultPanel QPlainTextEdit#structureJsonEditor { font-family: Consolas; font-size: 12px; color: #526581; border: 1px solid #DFE7F2; border-radius: 9px; background: #F8FAFD; padding: 7px; }
QFrame#structureResultPanel QLabel#jsonIdentity { font-size: 11px; color: #9B7435; }
QFrame#structureResultPanel QLineEdit { min-height: 30px; border-radius: 7px; font-size: 12px; }
QFrame#structureResultPanel QFrame#resultLogActivity { border: 0; border-radius: 11px; background: #F0F6FF; }
QFrame#structureResultPanel QLabel#resultLogActivityTitle { color: #2563EB; font-size: 13px; }
QFrame#structureResultPanel QLabel#resultLogActivityNote { color: #71819B; font-size: 11px; }
"""

APP_STYLESHEET += """
QPushButton#commitmentButton { min-height: 44px; padding: 0; background: #2563EB; color: white; border: 0; border-radius: 10px; }
QPushButton#commitmentButton:hover { background: #1D59DC; }
QPushButton#commitmentButton[committed="true"] { background: #009F6B; }
QPushButton#commitmentButton[committed="true"]:hover { background: #00885D; }
QPushButton#commitmentButton:disabled { background: #9EB8E6; color: #EEF4FF; }
"""

APP_STYLESHEET += """
QWidget#comparisonTab QFrame#comparisonChart,
QWidget#comparisonTab QFrame#comparisonTableCard, QWidget#comparisonTab QFrame#comparisonInspector { background: white; border: 1px solid #DFE7F7; border-radius: 14px; }
QWidget#comparisonTab QLabel { background: transparent; border: 0; color: #12213B; }
QWidget#comparisonTab QLabel#comparisonSectionTitle { font-size: 17px; }
QWidget#comparisonTab QToolButton#resultActionButton, QWidget#comparisonTab QPushButton#comparisonImport { border: 1px solid #DCE5F5; border-radius: 7px; background: #FCFDFF; padding: 0; }
QWidget#comparisonTab QToolButton#resultActionButton:hover, QWidget#comparisonTab QPushButton#comparisonImport:hover { background: #EDF4FF; }
QWidget#comparisonTab QLineEdit#comparisonSearch { border: 1px solid #DCE5F5; border-radius: 9px; min-height: 34px; font-size: 12px; padding: 0 10px; }
QWidget#comparisonTab QTableWidget#comparisonExperiments { background: white; border: 0; border-radius: 0; padding: 0; selection-background-color: #EAF2FF; selection-color: #12213B; }
QWidget#comparisonTab QHeaderView::section { background: #F3F6FF; border: 0; border-bottom: 1px solid #E4EBFA; color: #27345A; padding: 10px 8px; font-size: 12px; }
QWidget#comparisonTab QTableWidget#comparisonExperiments::item { padding: 8px; border-bottom: 1px solid #E9EEFA; }
QWidget#comparisonTab QTableWidget#comparisonExperiments::item:selected { background: #EAF2FF; }
QWidget#comparisonTab QScrollArea, QWidget#comparisonTab QWidget#inspectorBody { background: transparent; border: 0; }
QWidget#comparisonTab QLabel#inspectorName { font-size: 12px; color: #526581; min-height: 24px; }
QWidget#comparisonTab QLabel#inspectorValue { font-size: 12px; min-height: 24px; }
QWidget#comparisonTab QLabel#comparisonBadge { background: #E6EEFF; color: #2464DF; border-radius: 10px; padding: 4px 8px; font-size: 11px; }
QWidget#comparisonTab QFrame#comparisonDivider { border: 0; background: #DDE6F7; }
"""


APP_STYLESHEET += """
QMenu#comparisonControlPopup { background: white; border: 1px solid #D6E1F2; border-radius: 12px; padding: 2px; }
QWidget#comparisonPopupBody { background: white; border: 0; }
QComboBox#comparisonCombo { min-height: 38px; background: white; color: #101B38; border: 1px solid #D6E1F2; border-radius: 10px; padding: 0 12px; }
QComboBox#comparisonCombo:hover, QComboBox#comparisonCombo:focus, QComboBox#comparisonCombo:on { border-color: #7AACFF; background: #F7FBFF; }
QComboBox#comparisonCombo::drop-down { subcontrol-origin: border; subcontrol-position: right; width: 28px; border: 0; }
QComboBox#comparisonCombo::down-arrow { image: url($RESOURCE/parameter_chevron.svg); width: 18px; height: 18px; }
QComboBox#comparisonCombo QAbstractItemView { color: #101B38; background: white; border: 1px solid #D6E1F2; border-radius: 8px; padding: 4px; selection-background-color: #E9F2FF; selection-color: #2464DF; outline: 0; }
QComboBox#comparisonCombo QAbstractItemView::item { min-height: 34px; padding: 4px 10px; border: 0; }
QComboBox#comparisonCombo QAbstractItemView::item:selected { background: #E9F2FF; color: #2464DF; }
""".replace("$RESOURCE", _PARAMETER_RESOURCES)


APP_STYLESHEET += """
QListView#comparisonComboList { color: #101B38; background: white; border: 1px solid #D6E1F2; border-radius: 8px; padding: 4px; selection-background-color: #E9F2FF; selection-color: #2464DF; outline: 0; }
QListView#comparisonComboList::item { min-height: 34px; padding: 4px 10px; border: 0; border-radius: 6px; }
QListView#comparisonComboList::item:selected, QListView#comparisonComboList::item:hover { background: #E9F2FF; color: #2464DF; }
QFrame#experimentParameterPanel QPushButton#primaryButton:disabled { background: #9EB8E6; border-color: #9EB8E6; color: #EEF4FF; }
"""

APP_STYLESHEET += """
QScrollBar:horizontal { background: #F1F5FB; height: 8px; border: 0; border-radius: 4px; margin: 0; }
QScrollBar::handle:horizontal { background: #B9CBE2; border-radius: 4px; min-width: 28px; }
QScrollBar::handle:horizontal:hover { background: #83ACDF; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; height: 0; border: 0; background: transparent; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
QComboBox { combobox-popup: 0; }
QListView#parameterComboList { color: #101B38; background: white; border: 1px solid #D6E1F2; border-radius: 10px; padding: 6px; outline: 0; }
QListView#parameterComboList::item { min-height: 36px; padding: 6px 10px; border-radius: 7px; }
QListView#parameterComboList::item:selected, QListView#parameterComboList::item:hover { background: #E9F2FF; color: #2464DF; }
QPushButton#verifyStructureButton[verified="true"], QPushButton#verifyStructureButton[verified="true"]:disabled { background: #009F6B; color: white; }
QFrame#graphInspector QToolButton#graphInspectorClose { padding: 0; }
QToolButton#resultActionButton::menu-indicator { image: none; width: 0; }
QDialog#experimentReplay { background: #FFFFFF; border: 1px solid #DCE5F5; border-radius: 16px; }
QWidget#comparisonPopupBody QSpinBox { min-height: 32px; }
"""

APP_STYLESHEET += """
QSpinBox#comparisonRange { background: white; border: 1px solid #D6E1F2; border-radius: 9px; padding: 0 22px 0 10px; min-height: 36px; }
QSpinBox#comparisonRange:focus { border-color: #3B82F6; }
QSpinBox#comparisonRange::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 17px; height: 13px; margin: 4px 4px 0 0; background: #F1F5FC; border: 0; border-radius: 4px; }
QSpinBox#comparisonRange::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 17px; height: 13px; margin: 0 4px 4px 0; background: #F1F5FC; border: 0; border-radius: 4px; }
QSpinBox#comparisonRange::up-arrow { image: url($RESOURCE/parameter_up.svg); width: 12px; height: 12px; }
QSpinBox#comparisonRange::down-arrow { image: url($RESOURCE/parameter_down.svg); width: 12px; height: 12px; }
QWidget#comparisonTab QPushButton#primaryButton:disabled { background: #EAECF0; border-color: #EAECF0; color: #98A2B3; }
""".replace("$RESOURCE", _PARAMETER_RESOURCES)

APP_STYLESHEET += """
QWidget#comparisonTab QWidget#comparisonScrollContent { background: #F5F7FA; }
QWidget#comparisonTab QComboBox#comparisonCombo { min-height: 30px; max-height: 34px; padding-left: 8px; padding-right: 25px; font-size: 11px; }
QWidget#comparisonTab QComboBox#comparisonCombo[compactParameter="true"] { padding-left: 7px; padding-right: 0; }
QWidget#comparisonTab QComboBox#comparisonCombo[compactParameter="true"]::drop-down { width: 22px; }
QWidget#comparisonTab QComboBox#comparisonCombo[compactParameter="true"]::down-arrow { width: 14px; height: 14px; }
QWidget#comparisonTab QToolButton#comparisonExport, QWidget#comparisonTab QToolButton#comparisonFilterToggle { min-height: 30px; padding: 0; border: 1px solid #DCE5F5; border-radius: 8px; background: white; }
QWidget#comparisonTab QToolButton#comparisonExport::menu-indicator { image: none; width: 0; }
QWidget#comparisonTab QPushButton#comparisonSectionToggle { background: transparent; border: 0; padding: 0; min-height: 30px; font-size: 17px; text-align: left; }
QWidget#comparisonTab QPushButton#comparisonSectionToggle:hover { color: #2464FF; }
QWidget#comparisonTab QFrame#comparisonInspector QPushButton#comparisonSectionToggle { font-size: 15px; }
QWidget#comparisonTab QFrame#comparisonInspector QPushButton[comparisonAction="true"] { min-height: 42px; max-height: 42px; padding: 0 12px; }
QWidget#comparisonTab QPushButton#comparisonDelete { background: #FFF0F2; border: 1px solid #F2C6CD; color: #BF4053; }
QWidget#comparisonTab QPushButton#comparisonDelete:hover { background: #FFE1E7; border-color: #E9A2AF; }
QWidget#comparisonTab QPushButton#comparisonDelete:pressed { background: #FCD1DA; }
QWidget#comparisonTab QPushButton#comparisonDelete:disabled { background: #FFF7F8; border-color: #F2E1E5; color: #CFA5AD; }
QWidget#comparisonTab QWidget#comparisonInspectorViewport,
QWidget#comparisonTab QWidget#inspectorBody, QWidget#comparisonTab QWidget#comparisonPanelContent { background: white; }
QWidget#comparisonTab QWidget#comparisonExperimentsPanel, QWidget#comparisonTab QWidget#comparisonExperimentsDock { background: transparent; }
"""
