import sys
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QLineEdit, QTextEdit, QListWidget, 
    QStackedWidget, QFileDialog, QMessageBox, QFrame, QInputDialog,
    QComboBox, QGroupBox, QListWidgetItem, QProgressBar
)
from PySide6.QtCore import Qt, QTimer, QSize, QThread, Signal
from PySide6.QtGui import QFont, QPixmap, QImage, QColor, QPainter

from app.persistence.sqlite_db import SQLiteDB
from app.services.session_manager import SessionManager
from app.services.issue_processor import IssueProcessor
from app.models.entities import Project, Session, Issue

class ExportWorker(QThread):
    progress = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, processor, issue_id, output_dir):
        super().__init__()
        self.processor = processor
        self.issue_id = issue_id
        self.output_dir = output_dir

    def run(self):
        try:
            result_path = self.processor.process_issue(
                self.issue_id, 
                self.output_dir, 
                progress_callback=self.progress.emit
            )
            self.finished.emit(result_path)
        except Exception as e:
            self.error.emit(str(e))

class MainWin(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Review Capture Assist")
        self.resize(1100, 850)

        # Persistence & Services
        db_path = os.path.join(os.path.expanduser("~"), ".review_capture", "app.db")
        self.db = SQLiteDB(db_path)
        self.session_manager = SessionManager(self.db)
        self.issue_processor = IssueProcessor(self.db, self.session_manager.fs)

        # UI Components
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)

        self.init_main_screen()
        self.init_project_screen()
        self.init_active_session_screen()
        self.init_export_screen()

        self.stacked_widget.setCurrentIndex(0)
        self.refresh_projects()
        self.refresh_audio_devices()

        # Thumbnail timer
        self.thumb_timer = QTimer()
        self.thumb_timer.timeout.connect(self.update_live_thumbnail)
        self.thumb_timer.start(1000) # Update every second

    def init_main_screen(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header
        header_layout = QHBoxLayout()
        header_label = QLabel("Proyectos de Revisión")
        header_label.setFont(QFont("Arial", 20, QFont.Bold))
        header_label.setStyleSheet("color: #212529;")
        header_layout.addWidget(header_label)
        
        btn_export_view = QPushButton("Procesar y Exportar Issues")
        btn_export_view.setMinimumHeight(35)
        btn_export_view.setStyleSheet("background-color: #6c757d; color: white; border-radius: 6px; padding: 0 15px;")
        btn_export_view.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(3))
        header_layout.addWidget(btn_export_view)
        
        layout.addLayout(header_layout)

        # Content Layout (Horizontal: Left for Lists, Right for Settings)
        content_box = QHBoxLayout()
        layout.addLayout(content_box)

        # Left Side: Projects and Sessions
        left_side = QVBoxLayout()
        content_box.addLayout(left_side, 2)

        # 1. Projects Section
        proj_group = QGroupBox("1. Seleccione un Proyecto")
        proj_group.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #dee2e6; border-radius: 8px; margin-top: 10px; padding-top: 15px; }")
        proj_layout = QVBoxLayout(proj_group)
        self.project_list = QListWidget()
        self.project_list.setStyleSheet("border: none; background: transparent; font-size: 13px;")
        self.project_list.itemClicked.connect(self.on_project_selected)
        proj_layout.addWidget(self.project_list)
        left_side.addWidget(proj_group, 1)

        # 2. Sessions Section
        sess_group = QGroupBox("2. Sesiones de este Proyecto")
        sess_group.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #dee2e6; border-radius: 8px; margin-top: 10px; padding-top: 15px; }")
        sess_layout = QVBoxLayout(sess_group)
        self.lbl_sess_instruction = QLabel("Seleccione un proyecto arriba para ver sus sesiones")
        self.lbl_sess_instruction.setStyleSheet("color: #6c757d; font-style: italic; padding: 10px;")
        self.lbl_sess_instruction.setAlignment(Qt.AlignCenter)
        self.session_list = QListWidget()
        self.session_list.setStyleSheet("border: none; background: transparent; font-size: 13px;")
        self.session_list.setVisible(False)
        sess_layout.addWidget(self.lbl_sess_instruction)
        sess_layout.addWidget(self.session_list)
        left_side.addWidget(sess_group, 1)

        # Right Side: Global Settings
        right_side = QVBoxLayout()
        content_box.addLayout(right_side, 1)

        audio_settings_group = QGroupBox("Configuración de Audio")
        audio_settings_group.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #0d6efd; border-radius: 8px; margin-top: 10px; padding-top: 15px; color: #0d6efd; }")
        audio_settings_layout = QVBoxLayout(audio_settings_group)
        
        audio_settings_layout.addWidget(QLabel("Dispositivo de entrada:"))
        self.combo_audio_devices = QComboBox()
        self.combo_audio_devices.currentIndexChanged.connect(self.on_audio_device_changed)
        audio_settings_layout.addWidget(self.combo_audio_devices)

        # Test Audio Area
        test_audio_box = QGroupBox("Prueba de audio")
        test_audio_layout = QVBoxLayout(test_audio_box)
        self.btn_test_rec = QPushButton("Grabar 3s")
        self.btn_test_rec.clicked.connect(self.test_audio_recording)
        self.btn_test_play = QPushButton("Reproducir prueba")
        self.btn_test_play.setEnabled(False)
        self.btn_test_play.clicked.connect(self.test_audio_playback)
        test_audio_layout.addWidget(self.btn_test_rec)
        test_audio_layout.addWidget(self.btn_test_play)
        audio_settings_layout.addWidget(test_audio_box)
        
        right_side.addWidget(audio_settings_group)
        right_side.addStretch()

        # Footer Actions
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_new_proj = QPushButton("Nuevo Proyecto")
        btn_new_proj.setMinimumHeight(40)
        btn_new_proj.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px;")
        btn_new_proj.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(1))
        
        self.btn_start_session = QPushButton("Nueva Sesión")
        self.btn_start_session.setMinimumHeight(40)
        self.btn_start_session.setStyleSheet("""
            QPushButton { background-color: #0d6efd; color: white; border-radius: 6px; font-weight: bold; }
            QPushButton:disabled { background-color: #e9ecef; color: #adb5bd; }
        """)
        self.btn_start_session.clicked.connect(self.prepare_session)
        self.btn_start_session.setEnabled(False)

        self.btn_resume_session = QPushButton("Continuar Sesión")
        self.btn_resume_session.setMinimumHeight(40)
        self.btn_resume_session.setStyleSheet("""
            QPushButton { background-color: #198754; color: white; border-radius: 6px; font-weight: bold; }
            QPushButton:disabled { background-color: #e9ecef; color: #adb5bd; }
        """)
        self.btn_resume_session.clicked.connect(self.resume_selected_session)
        self.btn_resume_session.setEnabled(False)
        
        btn_layout.addWidget(btn_new_proj)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_start_session)
        btn_layout.addWidget(self.btn_resume_session)
        layout.addLayout(btn_layout)

        self.stacked_widget.addWidget(page)

    def refresh_audio_devices(self):
        self.combo_audio_devices.clear()
        devices = self.session_manager.audio_recorder.get_devices()
        for d in devices:
            self.combo_audio_devices.addItem(d['name'], d['index'])
        
        # Select default if any
        if self.combo_audio_devices.count() > 0:
            self.combo_audio_devices.setCurrentIndex(0)

    def on_audio_device_changed(self, index):
        device_idx = self.combo_audio_devices.currentData()
        self.session_manager.audio_recorder.set_device(device_idx)

    def test_audio_recording(self):
        self.btn_test_rec.setEnabled(False)
        self.btn_test_rec.setText("Grabando...")
        temp_file = os.path.join(os.path.expanduser("~"), ".review_capture", "test_audio.wav")
        os.makedirs(os.path.dirname(temp_file), exist_ok=True)
        
        try:
            self.session_manager.audio_recorder.start_recording(temp_file)
            # Record for 3 seconds
            QTimer.singleShot(3000, lambda: self.finish_test_audio(temp_file))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al iniciar prueba: {str(e)}")
            self.btn_test_rec.setEnabled(True)
            self.btn_test_rec.setText("Grabar 3s")

    def finish_test_audio(self, file_path):
        self.session_manager.audio_recorder.stop_recording()
        self.btn_test_rec.setEnabled(True)
        self.btn_test_rec.setText("Grabar 3s")
        self.btn_test_play.setEnabled(True)
        self._last_test_audio = file_path
        QMessageBox.information(self, "Prueba", "Grabación de prueba finalizada.")

    def test_audio_playback(self):
        if hasattr(self, '_last_test_audio'):
            self.session_manager.audio_recorder.play_file(self._last_test_audio)

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
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # Header
        header_frame = QFrame()
        header_frame.setStyleSheet("QFrame { background-color: #ffffff; border-bottom: 1px solid #e9ecef; padding-bottom: 10px; }")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(0, 0, 0, 10)
        info_layout = QVBoxLayout()
        self.lbl_project_info = QLabel("Proyecto: -")
        self.lbl_project_info.setFont(QFont("Arial", 18, QFont.Bold))
        self.lbl_project_info.setStyleSheet("color: #212529; border: none;")
        self.lbl_session_info = QLabel("Sesión: -")
        self.lbl_session_info.setFont(QFont("Arial", 10))
        self.lbl_session_info.setStyleSheet("color: #6c757d; border: none;")
        info_layout.addWidget(self.lbl_project_info)
        info_layout.addWidget(self.lbl_session_info)
        header_layout.addLayout(info_layout, 3)
        self.lbl_timer = QLabel("00:00:00")
        self.lbl_timer.setFont(QFont("Courier New", 24, QFont.Bold))
        self.lbl_timer.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_timer.setStyleSheet("color: #495057; border: none;")
        header_layout.addWidget(self.lbl_timer, 1)
        main_layout.addWidget(header_frame)

        # Body
        body_layout = QHBoxLayout()
        body_layout.setSpacing(20)
        main_layout.addLayout(body_layout)

        # Operation Column
        left_col = QVBoxLayout()
        left_col.setSpacing(15)
        body_layout.addLayout(left_col, 2)

        # a. Issue Management
        issue_group = QGroupBox("Issue actual")
        issue_group.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #f1f3f5; border-radius: 8px; margin-top: 10px; padding-top: 15px; }")
        issue_layout = QVBoxLayout(issue_group)
        self.lbl_active_issue = QLabel("Cargando issue...")
        self.lbl_active_issue.setFont(QFont("Arial", 11, QFont.Bold))
        self.lbl_active_issue.setStyleSheet("color: #0d6efd; padding: 5px;")
        issue_layout.addWidget(self.lbl_active_issue)
        self.btn_start_issue = QPushButton("Siguiente Issue")
        self.btn_start_issue.setMinimumHeight(40)
        self.btn_start_issue.clicked.connect(self.start_new_issue)
        issue_layout.addWidget(self.btn_start_issue)
        left_col.addWidget(issue_group)

        # b. Audio Toggle
        audio_group = QGroupBox("Grabación de audio")
        audio_group.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #f1f3f5; border-radius: 8px; margin-top: 10px; padding-top: 15px; }")
        audio_layout = QVBoxLayout(audio_group)
        self.btn_audio_large = QPushButton("● Grabación detenida")
        self.btn_audio_large.setMinimumHeight(50)
        self.btn_audio_large.setFont(QFont("Arial", 10, QFont.Bold))
        self.set_audio_button_style(False)
        self.btn_audio_large.clicked.connect(self.toggle_audio)
        audio_layout.addWidget(self.btn_audio_large)
        left_col.addWidget(audio_group)

        # c. Quick Note
        note_group = QGroupBox("Nota rápida")
        note_group.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #f1f3f5; border-radius: 8px; margin-top: 10px; padding-top: 15px; }")
        note_layout = QVBoxLayout(note_group)
        self.edit_note = QTextEdit()
        self.edit_note.setMinimumHeight(120) 
        self.edit_note.setPlaceholderText("Escriba una observación breve...")
        self.edit_note.setStyleSheet("border: 1px solid #dee2e6; border-radius: 4px; padding: 5px;")
        note_layout.addWidget(self.edit_note)
        self.btn_add_note = QPushButton("Agregar nota al issue")
        self.btn_add_note.setMinimumHeight(35)
        self.btn_add_note.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; padding: 5px;")
        self.btn_add_note.clicked.connect(self.add_note)
        note_layout.addWidget(self.btn_add_note)
        left_col.addWidget(note_group)

        # d. Screenshots
        cap_group = QGroupBox("Capturas de pantalla")
        cap_group.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #f1f3f5; border-radius: 8px; margin-top: 10px; padding-top: 15px; }")
        cap_layout = QVBoxLayout(cap_group)
        cap_ctrls = QHBoxLayout()
        self.combo_monitors = QComboBox()
        self.refresh_monitors()
        cap_ctrls.addWidget(QLabel("Monitor:"))
        cap_ctrls.addWidget(self.combo_monitors, 1)
        cap_layout.addLayout(cap_ctrls)
        self.lbl_thumbnail = QLabel("Vista previa")
        self.lbl_thumbnail.setFixedSize(240, 135) 
        self.lbl_thumbnail.setStyleSheet("border: 1px solid #dee2e6; background-color: #000; border-radius: 4px;")
        self.lbl_thumbnail.setAlignment(Qt.AlignCenter)
        cap_layout.addWidget(self.lbl_thumbnail, 0, Qt.AlignCenter)
        self.btn_screenshot = QPushButton("Tomar Captura")
        self.btn_screenshot.setMinimumHeight(45)
        self.btn_screenshot.setFont(QFont("Arial", 11, QFont.Bold))
        self.btn_screenshot.setStyleSheet("background-color: #0d6efd; color: white; border-radius: 6px;")
        self.btn_screenshot.clicked.connect(self.take_screenshot)
        cap_layout.addWidget(self.btn_screenshot)
        left_col.addWidget(cap_group)

        # Support Column
        right_col = QVBoxLayout()
        right_col.setSpacing(15)
        body_layout.addLayout(right_col, 1)

        right_col.addWidget(QLabel("Issues registrados:"))
        self.issue_list = QListWidget()
        self.issue_list.setStyleSheet("border: 1px solid #f1f3f5; border-radius: 4px; background: #fdfdfe;")
        self.issue_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.issue_list.customContextMenuRequested.connect(self.show_issue_context_menu)
        right_col.addWidget(self.issue_list, 2)

        right_col.addWidget(QLabel("Eventos recientes:"))
        self.event_feed = QListWidget()
        self.event_feed.setStyleSheet("font-size: 10px; color: #adb5bd; border: 1px solid #f1f3f5; border-radius: 4px; background: #fdfdfe;")
        right_col.addWidget(self.event_feed, 3)

        # Footer
        footer_layout = QHBoxLayout()
        footer_layout.addStretch()
        btn_finish_session = QPushButton("Finalizar Sesión")
        btn_finish_session.setMinimumSize(180, 40)
        btn_finish_session.setStyleSheet("background-color: #ffffff; color: #dc3545; font-weight: bold; border: 1px solid #dc3545; border-radius: 6px;")
        btn_finish_session.clicked.connect(self.stop_session)
        footer_layout.addWidget(btn_finish_session)
        footer_layout.addStretch()
        main_layout.addLayout(footer_layout)

        self.stacked_widget.addWidget(page)

        # Timers
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui_timer)

    def init_export_screen(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)
        header = QLabel("Procesamiento y Exportación de Issue")
        header.setFont(QFont("Arial", 18, QFont.Bold))
        layout.addWidget(header)
        grid = QVBoxLayout()
        layout.addLayout(grid)
        grid.addWidget(QLabel("1. Seleccione Proyecto:"))
        self.exp_proj_list = QListWidget()
        self.exp_proj_list.setMaximumHeight(100)
        self.exp_proj_list.itemClicked.connect(self.on_exp_project_selected)
        grid.addWidget(self.exp_proj_list)
        grid.addWidget(QLabel("2. Seleccione Sesión:"))
        self.exp_sess_list = QListWidget()
        self.exp_sess_list.setMaximumHeight(100)
        self.exp_sess_list.itemClicked.connect(self.on_exp_session_selected)
        grid.addWidget(self.exp_sess_list)
        grid.addWidget(QLabel("3. Seleccione el Issue a procesar:"))
        self.exp_issue_list = QListWidget()
        self.exp_issue_list.setMaximumHeight(120)
        grid.addWidget(self.exp_issue_list)
        grid.addWidget(QLabel("4. Directorio de salida:"))
        out_layout = QHBoxLayout()
        self.edit_exp_path = QLineEdit()
        self.edit_exp_path.setReadOnly(True)
        btn_exp_browse = QPushButton("Elegir Carpeta...")
        btn_exp_browse.clicked.connect(self.browse_exp_path)
        out_layout.addWidget(self.edit_exp_path)
        out_layout.addWidget(btn_exp_browse)
        grid.addLayout(out_layout)
        self.exp_progress_label = QLabel("Esperando inicio...")
        self.exp_progress_label.setStyleSheet("color: #6c757d; font-style: italic;")
        layout.addWidget(self.exp_progress_label)
        self.exp_log = QListWidget()
        self.exp_log.setStyleSheet("font-family: Consolas; font-size: 10px; background-color: #f8f9fa;")
        layout.addWidget(self.exp_log)
        btn_box = QHBoxLayout()
        btn_cancel = QPushButton("Volver")
        btn_cancel.setMinimumHeight(40)
        btn_cancel.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        self.btn_run_export = QPushButton("Procesar Issue")
        self.btn_run_export.setMinimumHeight(40)
        self.btn_run_export.setStyleSheet("background-color: #0d6efd; color: white; font-weight: bold; border-radius: 6px;")
        self.btn_run_export.clicked.connect(self.run_export)
        btn_box.addWidget(btn_cancel)
        btn_box.addStretch()
        btn_box.addWidget(self.btn_run_export)
        layout.addLayout(btn_box)
        self.stacked_widget.addWidget(page)

    def on_exp_project_selected(self, item):
        idx = self.exp_proj_list.currentRow()
        if idx < 0: return
        project = self.projects[idx]
        self.exp_sess_list.clear()
        self.exp_issue_list.clear()
        sessions = self.db.get_sessions_by_project(project.project_id)
        self._exp_sessions = sessions
        for s in sessions:
            self.exp_sess_list.addItem(f"{s.title} ({s.start_time.split('T')[0]})")

    def on_exp_session_selected(self, item):
        idx = self.exp_sess_list.currentRow()
        if idx < 0: return
        session = self._exp_sessions[idx]
        self.exp_issue_list.clear()
        issues = self.db.get_issues_by_session(session.session_id)
        self._exp_issues = issues
        for iss in issues:
            self.exp_issue_list.addItem(f"{iss.title} ({iss.status})")

    def browse_exp_path(self):
        path = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta de Salida")
        if path:
            self.edit_exp_path.setText(path)

    def run_export(self):
        issue_idx = self.exp_issue_list.currentRow()
        output_dir = self.edit_exp_path.text()
        if issue_idx < 0:
            QMessageBox.warning(self, "Error", "Seleccione un Issue")
            return
        if not output_dir:
            QMessageBox.warning(self, "Error", "Seleccione un directorio de salida")
            return
        issue = self._exp_issues[issue_idx]
        self.btn_run_export.setEnabled(False)
        self.exp_log.clear()
        self.exp_progress_label.setText("Procesando...")
        self.export_thread = ExportWorker(self.issue_processor, issue.issue_id, output_dir)
        self.export_thread.progress.connect(self.on_export_progress)
        self.export_thread.finished.connect(self.on_export_finished)
        self.export_thread.error.connect(self.on_export_error)
        self.export_thread.start()

    def on_export_progress(self, msg):
        self.exp_log.insertItem(0, msg)
        self.exp_progress_label.setText(msg)

    def on_export_finished(self, path):
        self.btn_run_export.setEnabled(True)
        self.exp_progress_label.setText("Exportación completada")
        QMessageBox.information(self, "Éxito", f"Issue procesado correctamente.\nResultado en: {path}")

    def on_export_error(self, err):
        self.btn_run_export.setEnabled(True)
        self.exp_progress_label.setText("Error en el proceso")
        QMessageBox.critical(self, "Error", f"Error al procesar issue: {err}")

    def set_audio_button_style(self, is_recording):
        if is_recording:
            self.btn_audio_large.setText("■ Grabación en curso")
            self.btn_audio_large.setStyleSheet("QPushButton { background-color: #DC2626; color: white; border-radius: 6px; }")
        else:
            self.btn_audio_large.setText("● Grabación detenida")
            self.btn_audio_large.setStyleSheet("QPushButton { background-color: #E9EEF5; color: #1F2937; border-radius: 6px; }")

    def toggle_audio(self):
        is_recording = self.session_manager.toggle_audio_recording()
        self.set_audio_button_style(is_recording)
        if is_recording:
            self.event_feed.insertItem(0, f"[{datetime.now().strftime('%H:%M:%S')}] Grabación de audio iniciada")
        else:
            self.event_feed.insertItem(0, f"[{datetime.now().strftime('%H:%M:%S')}] Grabación de audio detenida")
        self.sync_issue_ui()

    def sync_issue_ui(self):
        if not self.session_manager.active_session: return
        issues = self.db.get_issues_by_session(self.session_manager.active_session.session_id)
        next_num = len(issues) + (0 if self.session_manager.active_issue else 1)
        if self.session_manager.active_issue:
            self.lbl_active_issue.setText(f"Activo: {self.session_manager.active_issue.title}")
            has_content = self.session_manager.active_issue_has_content
            self.btn_start_issue.setEnabled(has_content)
            self.btn_start_issue.setText(f"Siguiente Issue (#{len(issues)+1})")
        else:
            self.lbl_active_issue.setText("Ninguno")
            self.btn_start_issue.setEnabled(True)

    def start_session_ui(self, session, project_name):
        self.lbl_project_info.setText(f"Proyecto: {project_name}")
        self.lbl_session_info.setText(f"Sesión: {session.title}")
        self.session_start_time = datetime.now()
        self.timer.start(1000)
        self.stacked_widget.setCurrentIndex(2)
        self.sync_issue_ui()
        self.refresh_issue_list()

    def start_new_issue(self):
        issues = self.db.get_issues_by_session(self.session_manager.active_session.session_id)
        next_num = len(issues) + 1
        title, ok = QInputDialog.getText(self, "Nuevo Issue", f"Título del Issue #{next_num} (opcional):")
        if not ok: return
        final_title = title if title else f"Issue #{next_num}"
        self.session_manager.start_issue(final_title)
        self.event_feed.insertItem(0, f"[{datetime.now().strftime('%H:%M:%S')}] Nuevo issue iniciado: {final_title}")
        self.sync_issue_ui()
        self.refresh_issue_list()

    def stop_current_issue(self):
        issue = self.session_manager.stop_issue(auto_start_next=False)
        self.event_feed.insertItem(0, f"[{datetime.now().strftime('%H:%M:%S')}] Issue finalizado: {issue.title}")
        self.sync_issue_ui()
        self.refresh_issue_list()

    def refresh_issue_list(self):
        self.issue_list.clear()
        if not self.session_manager.active_session: return
        issues = self.db.get_issues_by_session(self.session_manager.active_session.session_id)
        for iss in issues:
            status_icon = "●" if iss.status == "active" else "✓"
            item = QListWidgetItem(f"{status_icon} {iss.title}")
            if iss.status == "active":
                item.setForeground(QColor("#0d6efd"))
            self.issue_list.addItem(item)

    def add_note(self):
        text = self.edit_note.toPlainText()
        if not text: return
        self.session_manager.add_quick_note(text)
        self.event_feed.insertItem(0, f"[{datetime.now().strftime('%H:%M:%S')}] Nota agregada")
        self.edit_note.clear()
        self.sync_issue_ui()

    def update_ui_timer(self):
        delta = datetime.now() - self.session_start_time
        self.lbl_timer.setText(f"{int(delta.total_seconds()//3600):02d}:{int((delta.total_seconds()%3600)//60):02d}:{int(delta.total_seconds()%60):02d}")

    def refresh_projects(self):
        self.project_list.clear()
        self.exp_proj_list.clear()
        self.projects = self.db.get_projects()
        for p in self.projects:
            self.project_list.addItem(f"{p.name} ({p.code})")
            self.exp_proj_list.addItem(f"{p.name} ({p.code})")

    def on_project_selected(self, item):
        idx = self.project_list.currentRow()
        if idx < 0: return
        self.btn_start_session.setEnabled(True)
        self.refresh_sessions(self.projects[idx].project_id)
        self.lbl_sess_instruction.setVisible(False)
        self.session_list.setVisible(True)

    def refresh_sessions(self, project_id):
        self.session_list.clear()
        self.sessions = self.db.get_sessions_by_project(project_id)
        for s in self.sessions:
            self.session_list.addItem(f"{s.title} ({s.start_time.split('T')[0]})")
        self.btn_resume_session.setEnabled(False)
        self.session_list.itemClicked.connect(lambda: self.btn_resume_session.setEnabled(True))

    def refresh_monitors(self):
        self.combo_monitors.clear()
        monitors = self.session_manager.screenshot_service.get_monitors()
        for i, mon in enumerate(monitors):
            self.combo_monitors.addItem(f"Monitor {i}", i)

    def update_live_thumbnail(self):
        if self.stacked_widget.currentIndex() != 2: return
        mon_idx = self.combo_monitors.currentData()
        if mon_idx is None: return
        try:
            import mss
            with mss.mss() as sct:
                sct_img = sct.grab(sct.monitors[mon_idx])
                img = QImage(sct_img.bgra, sct_img.size[0], sct_img.size[1], QImage.Format_ARGB32)
                self.lbl_thumbnail.setPixmap(QPixmap.fromImage(img).scaled(self.lbl_thumbnail.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except: pass

    def browse_path(self):
        path = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta")
        if path: self.edit_proj_path.setText(path)

    def save_project(self):
        p = Project(name=self.edit_proj_name.text(), code=self.edit_proj_code.text(), default_storage_root=self.edit_proj_path.text())
        self.db.save_project(p)
        self.refresh_projects()
        self.stacked_widget.setCurrentIndex(0)

    def prepare_session(self):
        p = self.projects[self.project_list.currentRow()]
        title, ok = QInputDialog.getText(self, "Nueva Sesión", "Título:", text=self.session_manager.get_next_revision_title(p))
        if ok and title:
            self.start_session_ui(self.session_manager.start_session(p, title, "Tester"), p.name)

    def resume_selected_session(self):
        s = self.sessions[self.session_list.currentRow()]
        self.session_manager.resume_session(s.session_id)
        self.start_session_ui(s, self.projects[self.project_list.currentRow()].name)

    def take_screenshot(self):
        try:
            mon_idx = self.combo_monitors.currentData()
            shot = self.session_manager.take_manual_screenshot(monitor_index=mon_idx)
            self.event_feed.insertItem(0, f"[{datetime.now().strftime('%H:%M:%S')}] Captura realizada")
            self.sync_issue_ui()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al capturar: {str(e)}")

    def stop_session(self):
        self.timer.stop()
        self.session_manager.stop_session()
        self.stacked_widget.setCurrentIndex(0)
        self.refresh_projects()

    def show_issue_context_menu(self, position):
        item = self.issue_list.itemAt(position)
        if not item: return
        idx = self.issue_list.row(item)
        issues = self.db.get_issues_by_session(self.session_manager.active_session.session_id)
        issue = issues[idx]
        from PySide6.QtWidgets import QMenu
        menu = QMenu()
        if issue.status == "active": menu.addAction("Finalizar").triggered.connect(self.stop_current_issue)
        menu.addAction("Eliminar").triggered.connect(lambda: [self.db.delete_issue(issue.issue_id), self.refresh_issue_list(), self.sync_issue_ui()])
        menu.exec_(self.issue_list.mapToGlobal(position))

if __name__ == "__main__":
    from datetime import datetime
    app = QApplication(sys.argv)
    window = MainWin()
    window.show()
    sys.exit(app.exec())
