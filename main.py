import sys
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QLineEdit, QTextEdit, QListWidget, 
    QStackedWidget, QFileDialog, QMessageBox, QFrame, QInputDialog
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from app.persistence.sqlite_db import SQLiteDB
from app.services.session_manager import SessionManager
from app.models.entities import Project

class MainWin(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Review Capture Assist")
        self.resize(800, 600)

        # Persistence & Services
        db_path = os.path.join(os.path.expanduser("~"), ".review_capture", "app.db")
        self.db = SQLiteDB(db_path)
        self.session_manager = SessionManager(self.db)

        # UI Components
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)

        self.init_main_screen()
        self.init_project_screen()
        self.init_active_session_screen()

        self.stacked_widget.setCurrentIndex(0)
        self.refresh_projects()

    def init_main_screen(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        label = QLabel("Proyectos de Revisión")
        label.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(label)

        self.project_list = QListWidget()
        layout.addWidget(self.project_list)

        btn_layout = QHBoxLayout()
        btn_new_proj = QPushButton("Nuevo Proyecto")
        btn_new_proj.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(1))
        
        btn_start_session = QPushButton("Nueva Sesión")
        btn_start_session.clicked.connect(self.prepare_session)
        
        btn_layout.addWidget(btn_new_proj)
        btn_layout.addWidget(btn_start_session)
        layout.addLayout(btn_layout)

        self.stacked_widget.addWidget(page)

    def init_project_screen(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        layout.addWidget(QLabel("Configuración de Proyecto"))
        
        self.edit_proj_name = QLineEdit()
        self.edit_proj_name.setPlaceholderText("Nombre del Proyecto")
        layout.addWidget(self.edit_proj_name)

        self.edit_proj_code = QLineEdit()
        self.edit_proj_code.setPlaceholderText("Código (slug)")
        layout.addWidget(self.edit_proj_code)

        path_layout = QHBoxLayout()
        self.edit_proj_path = QLineEdit()
        self.edit_proj_path.setPlaceholderText("Ruta de almacenamiento")
        btn_browse = QPushButton("...")
        btn_browse.clicked.connect(self.browse_path)
        path_layout.addWidget(self.edit_proj_path)
        path_layout.addWidget(btn_browse)
        layout.addLayout(path_layout)

        btn_save = QPushButton("Guardar Proyecto")
        btn_save.clicked.connect(self.save_project)
        layout.addWidget(btn_save)

        btn_back = QPushButton("Volver")
        btn_back.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        layout.addWidget(btn_back)

        self.stacked_widget.addWidget(page)

    def init_active_session_screen(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        self.lbl_session_info = QLabel("Sesión Activa")
        self.lbl_session_info.setFont(QFont("Arial", 14, QFont.Bold))
        layout.addWidget(self.lbl_session_info)

        self.lbl_timer = QLabel("00:00:00")
        self.lbl_timer.setFont(QFont("Courier New", 24))
        self.lbl_timer.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_timer)

        # Controls
        ctrl_layout = QHBoxLayout()
        btn_screenshot = QPushButton("Tomar Captura")
        btn_screenshot.setMinimumHeight(50)
        btn_screenshot.clicked.connect(self.take_screenshot)
        
        btn_stop = QPushButton("Finalizar Sesión")
        btn_stop.setStyleSheet("background-color: #ff4444; color: white;")
        btn_stop.clicked.connect(self.stop_session)
        
        ctrl_layout.addWidget(btn_screenshot)
        ctrl_layout.addWidget(btn_stop)
        layout.addLayout(ctrl_layout)

        # Notes
        layout.addWidget(QLabel("Nota Rápida:"))
        self.edit_note = QTextEdit()
        self.edit_note.setMaximumHeight(100)
        layout.addWidget(self.edit_note)
        
        btn_add_note = QPushButton("Agregar Nota")
        btn_add_note.clicked.connect(self.add_note)
        layout.addWidget(btn_add_note)

        # Feed
        layout.addWidget(QLabel("Eventos Recientes:"))
        self.event_feed = QListWidget()
        layout.addWidget(self.event_feed)

        self.stacked_widget.addWidget(page)

        # Timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui_timer)

    # UI Logic
    def refresh_projects(self):
        self.project_list.clear()
        self.projects = self.db.get_projects()
        for p in self.projects:
            self.project_list.addItem(f"{p.name} ({p.code})")

    def browse_path(self):
        path = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta")
        if path:
            self.edit_proj_path.setText(path)

    def save_project(self):
        name = self.edit_proj_name.text()
        code = self.edit_proj_code.text()
        path = self.edit_proj_path.text()

        if not name or not path:
            QMessageBox.warning(self, "Error", "Faltan datos obligatorios")
            return

        project = Project(name=name, code=code, default_storage_root=path)
        self.db.save_project(project)
        self.refresh_projects()
        self.stacked_widget.setCurrentIndex(0)

    def prepare_session(self):
        idx = self.project_list.currentRow()
        if idx < 0:
            QMessageBox.warning(self, "Error", "Seleccione un proyecto")
            return
        
        project = self.projects[idx]
        
        # In MVP, we can just ask for a title
        title, ok = QInputDialog.getText(self, "Nueva Sesión", "Título de la sesión:")
        if not ok or not title:
            return

        session = self.session_manager.start_session(project, title, "Default Tester")
        self.lbl_session_info.setText(f"Sesión: {title} | Proyecto: {project.name}")
        self.event_feed.clear()
        self.event_feed.addItem(f"[{datetime.now().strftime('%H:%M:%S')}] Sesión iniciada")
        
        self.session_start_time = datetime.now()
        self.timer.start(1000)
        self.stacked_widget.setCurrentIndex(2)

    def update_ui_timer(self):
        delta = datetime.now() - self.session_start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        self.lbl_timer.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

    def take_screenshot(self):
        try:
            shot = self.session_manager.take_manual_screenshot()
            self.event_feed.insertItem(0, f"[{datetime.now().strftime('%H:%M:%S')}] Captura: {shot.file_name}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al capturar: {str(e)}")

    def add_note(self):
        text = self.edit_note.toPlainText()
        if not text:
            return
        self.session_manager.add_quick_note(text)
        self.event_feed.insertItem(0, f"[{datetime.now().strftime('%H:%M:%S')}] Nota agregada")
        self.edit_note.clear()

    def stop_session(self):
        self.timer.stop()
        session = self.session_manager.stop_session()
        QMessageBox.information(self, "Finalizado", f"Sesión guardada en:\n{session.storage_path}")
        self.stacked_widget.setCurrentIndex(0)

if __name__ == "__main__":
    from datetime import datetime
    app = QApplication(sys.argv)
    window = MainWin()
    window.show()
    sys.exit(app.exec())
