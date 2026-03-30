import sys
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QLineEdit, QTextEdit, QListWidget, 
    QStackedWidget, QFileDialog, QMessageBox, QFrame, QInputDialog,
    QComboBox, QGroupBox, QListWidgetItem
)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QFont, QPixmap, QImage, QColor, QPainter

from app.persistence.sqlite_db import SQLiteDB
from app.services.session_manager import SessionManager
from app.models.entities import Project, Session, Issue

class MainWin(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Review Capture Assist")
        self.resize(1000, 800)

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

        # Thumbnail timer
        self.thumb_timer = QTimer()
        self.thumb_timer.timeout.connect(self.update_live_thumbnail)
        self.thumb_timer.start(1000) # Update every second

    def init_main_screen(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        label = QLabel("Proyectos de Revisión")
        label.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(label)

        self.project_list = QListWidget()
        self.project_list.itemClicked.connect(self.on_project_selected)
        layout.addWidget(self.project_list)

        # Previous Sessions for selected project
        layout.addWidget(QLabel("Sesiones Previas (Seleccione un proyecto arriba):"))
        self.session_list = QListWidget()
        layout.addWidget(self.session_list)

        btn_layout = QHBoxLayout()
        btn_new_proj = QPushButton("Nuevo Proyecto")
        btn_new_proj.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(1))
        
        self.btn_start_session = QPushButton("Nueva Sesión")
        self.btn_start_session.clicked.connect(self.prepare_session)
        self.btn_start_session.setEnabled(False)

        self.btn_resume_session = QPushButton("Continuar Sesión")
        self.btn_resume_session.clicked.connect(self.resume_selected_session)
        self.btn_resume_session.setEnabled(False)
        
        btn_layout.addWidget(btn_new_proj)
        btn_layout.addWidget(self.btn_start_session)
        btn_layout.addWidget(self.btn_resume_session)
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
        main_layout = QVBoxLayout(page)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # --- 1. Header Superior de Contexto ---
        header_frame = QFrame()
        header_frame.setFrameShape(QFrame.StyledPanel)
        header_frame.setStyleSheet("background-color: #f8f9fa; border-radius: 8px; border: 1px solid #dee2e6;")
        header_layout = QHBoxLayout(header_frame)
        
        info_layout = QVBoxLayout()
        self.lbl_project_info = QLabel("Proyecto: -")
        self.lbl_project_info.setFont(QFont("Arial", 16, QFont.Bold))
        self.lbl_project_info.setStyleSheet("border: none; color: #212529;")
        
        self.lbl_session_info = QLabel("Sesión: -")
        self.lbl_session_info.setFont(QFont("Arial", 11))
        self.lbl_session_info.setStyleSheet("border: none; color: #6c757d;")
        
        info_layout.addWidget(self.lbl_project_info)
        info_layout.addWidget(self.lbl_session_info)
        header_layout.addLayout(info_layout, 3)

        self.lbl_timer = QLabel("00:00:00")
        self.lbl_timer.setFont(QFont("Courier New", 28, QFont.Bold))
        self.lbl_timer.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_timer.setStyleSheet("border: none; color: #0d6efd;")
        header_layout.addWidget(self.lbl_timer, 1)

        main_layout.addWidget(header_frame)

        # --- 2. Cuerpo Principal (Dos Columnas) ---
        body_layout = QHBoxLayout()
        main_layout.addLayout(body_layout)

        # Columna Principal Izquierda (Operación)
        left_col = QVBoxLayout()
        body_layout.addLayout(left_col, 2)

        # Bloque: Capturas de pantalla
        cap_group = QGroupBox("Capturas de pantalla")
        cap_layout = QVBoxLayout(cap_group)
        
        cap_ctrls = QHBoxLayout()
        self.combo_monitors = QComboBox()
        self.refresh_monitors()
        cap_ctrls.addWidget(QLabel("Monitor:"))
        cap_ctrls.addWidget(self.combo_monitors, 1)
        cap_layout.addLayout(cap_ctrls)

        preview_layout = QHBoxLayout()
        self.lbl_thumbnail = QLabel("Vista previa")
        self.lbl_thumbnail.setFixedSize(320, 180)
        self.lbl_thumbnail.setStyleSheet("border: 2px solid #adb5bd; background-color: black; border-radius: 4px;")
        self.lbl_thumbnail.setAlignment(Qt.AlignCenter)
        preview_layout.addStretch()
        preview_layout.addWidget(self.lbl_thumbnail)
        preview_layout.addStretch()
        cap_layout.addLayout(preview_layout)

        self.btn_screenshot = QPushButton("Tomar Captura")
        self.btn_screenshot.setMinimumHeight(50)
        self.btn_screenshot.setFont(QFont("Arial", 12, QFont.Bold))
        self.btn_screenshot.setStyleSheet("background-color: #0d6efd; color: white; border-radius: 6px;")
        self.btn_screenshot.clicked.connect(self.take_screenshot)
        cap_layout.addWidget(self.btn_screenshot)
        left_col.addWidget(cap_group)

        # Bloque: Grabación de audio
        audio_group = QGroupBox("Grabación de audio")
        audio_layout = QVBoxLayout(audio_group)
        
        status_layout = QHBoxLayout()
        self.lbl_audio_indicator = QLabel("○")
        self.lbl_audio_indicator.setFont(QFont("Arial", 24))
        self.lbl_audio_indicator.setStyleSheet("color: #6c757d;")
        self.lbl_audio_status_text = QLabel("Estado: Detenido")
        self.lbl_audio_status_text.setFont(QFont("Arial", 12, QFont.Bold))
        status_layout.addWidget(self.lbl_audio_indicator)
        status_layout.addWidget(self.lbl_audio_status_text)
        status_layout.addStretch()
        audio_layout.addLayout(status_layout)

        self.btn_audio_toggle = QPushButton("Iniciar grabación")
        self.btn_audio_toggle.setMinimumHeight(40)
        self.btn_audio_toggle.clicked.connect(self.toggle_audio)
        audio_layout.addWidget(self.btn_audio_toggle)
        left_col.addWidget(audio_group)

        # Bloque: Gestión de issue
        issue_group = QGroupBox("Gestión de issue")
        issue_layout = QVBoxLayout(issue_group)
        
        self.lbl_active_issue = QLabel("Ningún issue activo")
        issue_font = QFont("Arial", 11)
        issue_font.setItalic(True)
        self.lbl_active_issue.setFont(issue_font)
        self.lbl_active_issue.setStyleSheet("color: #6c757d; padding: 5px;")
        issue_layout.addWidget(self.lbl_active_issue)

        issue_btns = QHBoxLayout()
        self.btn_start_issue = QPushButton("Nuevo issue")
        self.btn_start_issue.clicked.connect(self.start_new_issue)
        self.btn_stop_issue = QPushButton("Finalizar issue")
        self.btn_stop_issue.clicked.connect(self.stop_current_issue)
        self.btn_stop_issue.setEnabled(False)
        issue_btns.addWidget(self.btn_start_issue)
        issue_btns.addWidget(self.btn_stop_issue)
        issue_layout.addLayout(issue_btns)
        left_col.addWidget(issue_group)

        # Columna Lateral Derecha (Soporte)
        right_col = QVBoxLayout()
        body_layout.addLayout(right_col, 1)

        # Bloque: Nota rápida
        note_group = QGroupBox("Nota rápida")
        note_layout = QVBoxLayout(note_group)
        self.edit_note = QTextEdit()
        self.edit_note.setMaximumHeight(80)
        self.edit_note.setPlaceholderText("Escriba una observación breve...")
        note_layout.addWidget(self.edit_note)
        self.btn_add_note = QPushButton("Agregar nota")
        self.btn_add_note.clicked.connect(self.add_note)
        note_layout.addWidget(self.btn_add_note)
        right_col.addWidget(note_group)

        # Bloque: Issues registrados
        issues_reg_group = QGroupBox("Issues registrados en esta sesión")
        issues_reg_layout = QVBoxLayout(issues_reg_group)
        self.issue_list = QListWidget()
        self.issue_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.issue_list.customContextMenuRequested.connect(self.show_issue_context_menu)
        issues_reg_layout.addWidget(self.issue_list)
        right_col.addWidget(issues_reg_group)

        # Bloque: Eventos recientes
        event_group = QGroupBox("Eventos recientes")
        event_layout = QVBoxLayout(event_group)
        self.event_feed = QListWidget()
        self.event_feed.setStyleSheet("font-size: 10px; color: #495057;")
        event_layout.addWidget(self.event_feed)
        right_col.addWidget(event_group)

        # --- 3. Franja Inferior de Cierre ---
        footer_layout = QHBoxLayout()
        footer_layout.addStretch()
        btn_finish_session = QPushButton("Finalizar Sesión")
        btn_finish_session.setMinimumSize(200, 40)
        btn_finish_session.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #bb2d3b;
            }
        """)
        btn_finish_session.clicked.connect(self.stop_session)
        footer_layout.addWidget(btn_finish_session)
        footer_layout.addStretch()
        main_layout.addLayout(footer_layout)

        self.stacked_widget.addWidget(page)

        # Timers
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui_timer)

    def start_session_ui(self, session, project_name):
        self.lbl_project_info.setText(f"Proyecto: {project_name}")
        self.lbl_session_info.setText(f"Sesión: {session.title}")
        self.event_feed.clear()
        self.event_feed.addItem(f"[{datetime.now().strftime('%H:%M:%S')}] Sesión iniciada/reanudada")
        
        self.session_start_time = datetime.now()
        self.timer.start(1000)
        self.stacked_widget.setCurrentIndex(2)
        
        # Reset Audio and Issue UI
        self.lbl_audio_indicator.setText("○")
        self.lbl_audio_indicator.setStyleSheet("color: #6c757d;")
        self.lbl_audio_status_text.setText("Estado: Detenido")
        self.btn_audio_toggle.setText("Iniciar grabación")
        
        self.lbl_active_issue.setText("Ningún issue activo")
        self.lbl_active_issue.setStyleSheet("color: #6c757d; font-style: italic;")
        self.btn_start_issue.setEnabled(True)
        self.btn_stop_issue.setEnabled(False)

    def toggle_audio(self):
        is_recording = self.session_manager.toggle_audio_recording()
        if is_recording:
            self.btn_audio_toggle.setText("Detener grabación")
            self.lbl_audio_indicator.setText("●")
            self.lbl_audio_indicator.setStyleSheet("color: #dc3545;")
            self.lbl_audio_status_text.setText("Estado: Grabando")
            self.event_feed.insertItem(0, f"[{datetime.now().strftime('%H:%M:%S')}] Grabación de audio iniciada")
        else:
            self.btn_audio_toggle.setText("Iniciar grabación")
            self.lbl_audio_indicator.setText("○")
            self.lbl_audio_indicator.setStyleSheet("color: #6c757d;")
            self.lbl_audio_status_text.setText("Estado: Detenido")
            self.event_feed.insertItem(0, f"[{datetime.now().strftime('%H:%M:%S')}] Grabación de audio detenida")

    def start_new_issue(self):
        title, ok = QInputDialog.getText(self, "Nuevo Issue", "Título del Issue:")
        if not ok or not title:
            return
            
        issue = self.session_manager.start_issue(title)
        self.lbl_active_issue.setText(f"Issue activo: {title}")
        self.lbl_active_issue.setStyleSheet("font-weight: bold; color: #0d6efd;")
        self.btn_start_issue.setEnabled(False)
        self.btn_stop_issue.setEnabled(True)
        self.event_feed.insertItem(0, f"[{datetime.now().strftime('%H:%M:%S')}] Issue iniciado: {title}")
        self.refresh_issue_list()

    def stop_current_issue(self):
        issue = self.session_manager.stop_issue()
        self.lbl_active_issue.setText("Ningún issue activo")
        self.lbl_active_issue.setStyleSheet("color: #6c757d; font-style: italic;")
        self.btn_start_issue.setEnabled(True)
        self.btn_stop_issue.setEnabled(False)
        self.event_feed.insertItem(0, f"[{datetime.now().strftime('%H:%M:%S')}] Issue finalizado: {issue.title}")
        self.refresh_issue_list()

    def show_issue_context_menu(self, position):
        item = self.issue_list.itemAt(position)
        if not item: return
        
        from PySide6.QtWidgets import QMenu
        menu = QMenu()
        delete_action = menu.addAction("Eliminar Issue")
        action = menu.exec_(self.issue_list.mapToGlobal(position))
        
        if action == delete_action:
            idx = self.issue_list.row(item)
            issues = self.db.get_issues_by_session(self.session_manager.active_session.session_id)
            issue = issues[idx]
            
            confirm = QMessageBox.question(self, "Confirmar", f"¿Eliminar el issue '{issue.title}'?", 
                                         QMessageBox.Yes | QMessageBox.No)
            if confirm == QMessageBox.Yes:
                self.db.delete_issue(issue.issue_id)
                self.refresh_issue_list()
                self.event_feed.insertItem(0, f"[{datetime.now().strftime('%H:%M:%S')}] Issue eliminado: {issue.title}")

    def refresh_issue_list(self):
        self.issue_list.clear()
        if not self.session_manager.active_session: return
        issues = self.db.get_issues_by_session(self.session_manager.active_session.session_id)
        for iss in issues:
            item = QListWidgetItem(f"{iss.title} ({iss.status})")
            # In a full implementation, we could add a delete button here
            self.issue_list.addItem(item)

    def add_note(self):
        text = self.edit_note.toPlainText()
        if not text:
            return
        self.session_manager.add_quick_note(text)
        self.event_feed.insertItem(0, f"[{datetime.now().strftime('%H:%M:%S')}] Nota agregada")
        self.edit_note.clear()

    def update_ui_timer(self):
        delta = datetime.now() - self.session_start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        self.lbl_timer.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

    # UI Logic
    def refresh_projects(self):
        self.project_list.clear()
        self.projects = self.db.get_projects()
        for p in self.projects:
            self.project_list.addItem(f"{p.name} ({p.code})")

    def on_project_selected(self, item):
        idx = self.project_list.currentRow()
        if idx < 0: return
        project = self.projects[idx]
        self.btn_start_session.setEnabled(True)
        self.refresh_sessions(project.project_id)

    def refresh_sessions(self, project_id):
        self.session_list.clear()
        self.sessions = self.db.get_sessions_by_project(project_id)
        for s in self.sessions:
            date_str = s.start_time.split("T")[0] if s.start_time else "N/A"
            self.session_list.addItem(f"{s.title} ({date_str}) - {s.status}")
        self.btn_resume_session.setEnabled(False)
        self.session_list.itemClicked.connect(lambda: self.btn_resume_session.setEnabled(True))

    def refresh_monitors(self):
        self.combo_monitors.clear()
        monitors = self.session_manager.screenshot_service.get_monitors()
        for i, mon in enumerate(monitors):
            if i == 0:
                self.combo_monitors.addItem("Todos los monitores (Virtual)", 0)
            else:
                self.combo_monitors.addItem(f"Monitor {i}: {mon['width']}x{mon['height']}", i)
        self.combo_monitors.setCurrentIndex(1 if len(monitors) > 1 else 0)

    def update_live_thumbnail(self):
        if self.stacked_widget.currentIndex() != 2:
            return
            
        mon_idx = self.combo_monitors.currentData()
        if mon_idx is None: return
        try:
            import mss
            import mss.tools
            with mss.mss() as sct:
                monitor = sct.monitors[mon_idx]
                sct_img = sct.grab(monitor)
                # Convert to QImage
                img = QImage(sct_img.bgra, sct_img.size[0], sct_img.size[1], QImage.Format_ARGB32)
                pixmap = QPixmap.fromImage(img)
                scaled = pixmap.scaled(self.lbl_thumbnail.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.lbl_thumbnail.setPixmap(scaled)
        except Exception as e:
            self.lbl_thumbnail.setText("Error preview")

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
        if idx < 0: return
        project = self.projects[idx]
        
        suggested_title = self.session_manager.get_next_revision_title(project)
        title, ok = QInputDialog.getText(self, "Nueva Sesión", 
                                        f"Título de la sesión (Proyecto: {project.name}):",
                                        text=suggested_title)
        if not ok or not title:
            return

        session = self.session_manager.start_session(project, title, "Default Tester")
        self.start_session_ui(session, project.name)

    def resume_selected_session(self):
        idx = self.session_list.currentRow()
        if idx < 0: return
        session = self.sessions[idx]
        project_idx = self.project_list.currentRow()
        project_name = self.projects[project_idx].name
        
        self.session_manager.resume_session(session.session_id)
        self.start_session_ui(session, project_name)
        self.refresh_issue_list()

    def take_screenshot(self):
        try:
            mon_idx = self.combo_monitors.currentData()
            shot = self.session_manager.take_manual_screenshot(monitor_index=mon_idx)
            self.event_feed.insertItem(0, f"[{datetime.now().strftime('%H:%M:%S')}] Captura: {shot.file_name}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al capturar: {str(e)}")

    def stop_session(self):
        self.timer.stop()
        session = self.session_manager.stop_session()
        QMessageBox.information(self, "Finalizado", f"Sesión guardada en:\n{session.storage_path}")
        self.stacked_widget.setCurrentIndex(0)
        self.refresh_projects()

if __name__ == "__main__":
    from datetime import datetime
    app = QApplication(sys.argv)
    window = MainWin()
    window.show()
    sys.exit(app.exec())
