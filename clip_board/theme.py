COLORS = {
    "background": "#F6F8FA",
    "surface": "#FFFFFF",
    "surface_raised": "#F1F4F6",
    "surface_hover": "#E7EDF2",
    "border": "#D2DAE1",
    "grid_minor": "#E8EDF1",
    "grid_major": "#D6DEE5",
    "text": "#17212B",
    "text_muted": "#596775",
    "primary": "#0F766E",
    "primary_hover": "#0B655E",
    "primary_soft": "#DDF3EF",
    "accent": "#D85C28",
    "danger": "#C93636",
    "selection": "#0878C9",
}


APP_STYLESHEET = f"""
QMainWindow, QDialog {{
    background: {COLORS["background"]};
    color: {COLORS["text"]};
}}
QWidget {{
    color: {COLORS["text"]};
    font-size: 13px;
}}
QMenuBar, QMenu, QToolBar, QStatusBar {{
    background: {COLORS["surface"]};
    color: {COLORS["text"]};
}}
QMenuBar {{
    border-bottom: 1px solid {COLORS["border"]};
}}
QMenuBar::item:selected, QMenu::item:selected {{
    background: {COLORS["surface_hover"]};
}}
QToolBar {{
    border: 0;
    border-bottom: 1px solid {COLORS["border"]};
    spacing: 4px;
    padding: 5px 8px;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    min-width: 28px;
    min-height: 28px;
    padding: 3px;
}}
QToolButton:hover {{
    background: {COLORS["surface_hover"]};
    border-color: {COLORS["border"]};
}}
QToolButton:pressed, QToolButton:checked {{
    background: {COLORS["primary_soft"]};
    border-color: {COLORS["primary"]};
    color: {COLORS["text"]};
}}
QDockWidget {{
    color: {COLORS["text"]};
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}}
QDockWidget::title {{
    background: {COLORS["surface"]};
    border-bottom: 1px solid {COLORS["border"]};
    padding: 8px 10px;
    font-weight: 600;
}}
QListWidget, QTreeWidget, QTableWidget {{
    background: {COLORS["surface"]};
    border: 0;
    outline: 0;
}}
QListWidget::item {{
    border-radius: 5px;
    padding: 5px;
}}
QListWidget::item:hover {{
    background: {COLORS["surface_hover"]};
}}
QListWidget::item:selected {{
    background: {COLORS["primary_soft"]};
    color: {COLORS["text"]};
}}
QPushButton {{
    background: {COLORS["surface_raised"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 5px;
    min-height: 28px;
    padding: 3px 10px;
}}
QPushButton:hover {{
    background: {COLORS["surface_hover"]};
    border-color: #9EACB8;
}}
QPushButton:pressed {{
    background: {COLORS["primary_soft"]};
}}
QPushButton:disabled {{
    color: #9AA5AE;
    background: #F3F5F6;
}}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {COLORS["surface_raised"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 5px;
    min-height: 28px;
    padding: 2px 7px;
    selection-background-color: {COLORS["primary"]};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {COLORS["primary"]};
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: {COLORS["border"]};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 14px;
    margin: -5px 0;
    background: {COLORS["primary"]};
    border-radius: 7px;
}}
QScrollBar:vertical, QScrollBar:horizontal {{
    background: {COLORS["surface"]};
    border: 0;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: #AAB5BE;
    border-radius: 4px;
    min-height: 24px;
    min-width: 24px;
}}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
    background: #8F9DA8;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0;
    height: 0;
}}
QStatusBar {{
    border-top: 1px solid {COLORS["border"]};
}}
QSplitter::handle {{
    background: {COLORS["border"]};
}}
QToolTip {{
    background: {COLORS["surface_raised"]};
    color: {COLORS["text"]};
    border: 1px solid #9EACB8;
    padding: 4px;
}}
"""
