import sys
import os
import cv2
import numpy as np

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSlider, QTextEdit, QFrame, QSizePolicy
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap, QFont

# Añadir el directorio actual al path para poder importar detectorGestos
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from detectorGestos import DetectorGestos, ModoOperacion
except ImportError as e:
    print(f"Error fatal al importar DetectorGestos: {e}")
    sys.exit(1)


class CameraThread(QThread):
    """
    Hilo secundario para capturar la cámara y procesar con MediaPipe.
    Evita que la inferencia pesada congele la GUI.
    """
    new_frame = pyqtSignal(np.ndarray)
    status_update = pyqtSignal(str, str, float)  # modo, gesto, confianza
    log_message = pyqtSignal(str)

    def __init__(self, detector):
        super().__init__()
        self.detector = detector
        self.running = False
        self.cap = None
        
        # Variables Thread-Safe para actualizaciones en caliente
        self.pending_sensitivity = None
        self.pending_smoothness = None

    def run(self):
        self.running = True
        self.cap = cv2.VideoCapture(0)
        
        if not self.cap.isOpened():
            self.log_message.emit("Error: No se pudo acceder a la cámara.")
            self.running = False
            return
            
        self.log_message.emit("Cámara iniciada correctamente.")

        while self.running and self.cap.isOpened():
            # Actualizaciones seguras (Thread-Safe) enviadas desde la GUI
            if self.pending_sensitivity is not None:
                try:
                    self.detector.actualizar_sensibilidad(self.pending_sensitivity)
                    self.log_message.emit(f"Sensibilidad aplicada internamente: {self.pending_sensitivity:.2f}")
                except Exception as e:
                    self.log_message.emit(f"Error aplicando sensibilidad: {e}")
                self.pending_sensitivity = None
                
            if self.pending_smoothness is not None:
                self.detector.configuracion.suavizado_movimiento = self.pending_smoothness
                self.detector.suavizado = self.pending_smoothness
                self.pending_smoothness = None

            ret, frame = self.cap.read()
            if not ret:
                break

            # Espejar
            frame = cv2.flip(frame, 1)

            # Procesar el fotograma
            frame_procesado, info = self.detector.procesar_frame(frame)

            # Emitir la imagen
            self.new_frame.emit(frame_procesado)

            # Emitir el estado
            gesto_txt = info.gesto.value.upper() if (info and info.gesto) else "NINGUNO"
            confianza = info.confianza if info else 0.0
            modo_txt = self.detector.modo.value.upper()
            self.status_update.emit(modo_txt, gesto_txt, confianza)

            self.msleep(10)

        if self.cap:
            self.cap.release()
        self.log_message.emit("Cámara detenida.")

    def stop(self):
        self.running = False
        self.wait()


class GestureControlWindow(QMainWindow):
    """
    Ventana Principal en PyQt5.
    Estética Dark Mode tipo HUD Táctico, con soporte para atajos de teclado.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NOVA - Comando Táctico de Gestos")
        self.resize(1280, 720)
        self.setFocusPolicy(Qt.StrongFocus)
        
        # Inicializar el detector
        self.detector = DetectorGestos(modo="pantalla")
        self.detector.mostrar_interfaz = False
        
        self.camera_thread = None

        self.init_ui()
        self.apply_dark_theme()
        
        # Auto-Arrancar
        QTimer.singleShot(500, self.start_system)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ─── SIDEBAR ───
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(320)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(20, 20, 20, 20)
        sidebar_layout.setSpacing(15)

        title_lbl = QLabel("NOVA TÁCTICO")
        title_lbl.setObjectName("TitleLabel")
        title_lbl.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(title_lbl)
        
        sidebar_layout.addSpacing(10)

        # Modos Toggle
        mode_lbl = QLabel("Modo de Operación:")
        mode_lbl.setObjectName("SubtitleLabel")
        sidebar_layout.addWidget(mode_lbl)
        
        mode_layout = QHBoxLayout()
        self.btn_modo_pantalla = QPushButton("PANTALLA")
        self.btn_modo_pantalla.setObjectName("ModeButtonActive")
        self.btn_modo_pantalla.clicked.connect(lambda: self.set_mode("pantalla"))
        
        self.btn_modo_mesa = QPushButton("MESA")
        self.btn_modo_mesa.setObjectName("ModeButtonInactive")
        self.btn_modo_mesa.clicked.connect(lambda: self.set_mode("mesa"))
        
        mode_layout.addWidget(self.btn_modo_pantalla)
        mode_layout.addWidget(self.btn_modo_mesa)
        sidebar_layout.addLayout(mode_layout)

        sidebar_layout.addSpacing(10)

        # Estabilidad
        smooth_lbl = QLabel("Estabilidad (Suavizado):")
        smooth_lbl.setObjectName("SubtitleLabel")
        self.slider_smooth = QSlider(Qt.Horizontal)
        self.slider_smooth.setRange(1, 15)
        self.slider_smooth.setValue(5)
        self.slider_smooth.valueChanged.connect(self.on_smooth_change)
        sidebar_layout.addWidget(smooth_lbl)
        sidebar_layout.addWidget(self.slider_smooth)

        # Sensibilidad
        sens_lbl = QLabel("Sensibilidad:")
        sens_lbl.setObjectName("SubtitleLabel")
        self.slider_sens = QSlider(Qt.Horizontal)
        self.slider_sens.setRange(10, 100)
        self.slider_sens.setValue(70)
        self.slider_sens.valueChanged.connect(self.on_sens_change)
        sidebar_layout.addWidget(sens_lbl)
        sidebar_layout.addWidget(self.slider_sens)

        sidebar_layout.addSpacing(10)

        self.btn_calib = QPushButton("CALIBRAR (Mesa)")
        self.btn_calib.setObjectName("CalibButton")
        self.btn_calib.setEnabled(False)
        self.btn_calib.clicked.connect(self.start_calibration)
        sidebar_layout.addWidget(self.btn_calib)

        sidebar_layout.addStretch()

        # Ayuda de Teclado
        help_box = QFrame()
        help_box.setObjectName("HelpBox")
        help_layout = QVBoxLayout(help_box)
        help_layout.setContentsMargins(10, 10, 10, 10)
        help_lbl = QLabel(
            "<b>ATAJOS DE TECLADO</b><br><br>"
            "<b>[M]</b> Cambiar Modo<br>"
            "<b>[C]</b> Calibrar (Solo Mesa)<br>"
            "<b>[R]</b> Resetear Tracker<br>"
            "<b>[Q]</b> Salir del Sistema"
        )
        help_lbl.setObjectName("HelpText")
        help_layout.addWidget(help_lbl)
        sidebar_layout.addWidget(help_box)

        # Consola
        self.console = QTextEdit()
        self.console.setObjectName("Console")
        self.console.setReadOnly(True)
        self.console.setFixedHeight(120)
        sidebar_layout.addWidget(self.console)

        # ─── MAIN AREA ───
        self.main_area = QFrame()
        self.main_area.setObjectName("MainArea")
        main_area_layout = QVBoxLayout(self.main_area)
        main_area_layout.setContentsMargins(0, 0, 0, 0)
        main_area_layout.setSpacing(0)

        self.video_label = QLabel("INICIANDO SENSORES...")
        self.video_label.setObjectName("VideoLabel")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_area_layout.addWidget(self.video_label, stretch=1)

        self.hud_label = QLabel("ESTADO: EN ESPERA")
        self.hud_label.setObjectName("HUDLabel")
        self.hud_label.setFixedHeight(40)
        self.hud_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        main_area_layout.addWidget(self.hud_label)

        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(self.main_area, stretch=1)

    def apply_dark_theme(self):
        qss = """
        QMainWindow { background-color: #0b0f19; }
        #Sidebar { background-color: #111827; border-right: 1px solid #1f2937; }
        #MainArea { background-color: #000000; }
        #TitleLabel { color: #00ffcc; font-size: 22px; font-weight: 900; letter-spacing: 2px; }
        #SubtitleLabel { color: #9ca3af; font-size: 12px; font-weight: bold; margin-top: 5px; }
        QLabel { color: #e5e7eb; font-size: 13px; }
        
        QPushButton { font-size: 13px; font-weight: bold; padding: 10px; border-radius: 6px; border: none; color: white; }
        #ModeButtonActive { background-color: #10a37f; }
        #ModeButtonInactive { background-color: #374151; color: #9ca3af; }
        #ModeButtonInactive:hover { background-color: #4b5563; }
        
        #CalibButton { background-color: #f59e0b; color: #000000; }
        #CalibButton:hover { background-color: #d97706; }
        #CalibButton:disabled { background-color: #374151; color: #6b7280; }
        
        QSlider::groove:horizontal { border-radius: 3px; height: 6px; background: #374151; }
        QSlider::handle:horizontal { background: #00ffcc; width: 14px; margin: -4px 0; border-radius: 7px; }
        
        #HelpBox { background-color: #1f2937; border-radius: 6px; border: 1px solid #374151; }
        #HelpText { color: #d1d5db; font-size: 11px; line-height: 1.4; }
        
        #Console { background-color: #030712; color: #10b981; font-family: Consolas, monospace; font-size: 11px; border: 1px solid #1f2937; border-radius: 4px; padding: 6px; }
        #VideoLabel { background-color: #000000; color: #444444; font-size: 20px; font-weight: bold; }
        #HUDLabel { background-color: #0f172a; color: #00ffcc; font-family: Consolas, monospace; font-size: 14px; font-weight: bold; padding-left: 20px; border-top: 1px solid #1e293b; }
        """
        self.setStyleSheet(qss)

    def log_msg(self, text: str):
        self.console.append(f"> {text}")
        self.console.verticalScrollBar().setValue(self.console.verticalScrollBar().maximum())

    def start_system(self):
        self.log_msg("Arrancando IA de visión...")
        self.camera_thread = CameraThread(self.detector)
        self.camera_thread.new_frame.connect(self.update_video_frame)
        self.camera_thread.status_update.connect(self.update_hud)
        self.camera_thread.log_message.connect(self.log_msg)
        self.camera_thread.start()

    def set_mode(self, mode_str):
        if not self.detector: return
        
        if mode_str == "mesa":
            self.detector.modo = ModoOperacion.MESA
            self.detector._cambiar_modo()
            self.btn_modo_pantalla.setObjectName("ModeButtonInactive")
            self.btn_modo_mesa.setObjectName("ModeButtonActive")
            self.btn_calib.setEnabled(True)
            self.log_msg("Modo cambiado a MESA. Calibración lista.")
        else:
            self.detector.modo = ModoOperacion.PANTALLA
            self.detector._cambiar_modo()
            self.btn_modo_pantalla.setObjectName("ModeButtonActive")
            self.btn_modo_mesa.setObjectName("ModeButtonInactive")
            self.btn_calib.setEnabled(False)
            self.log_msg("Modo cambiado a PANTALLA.")
            
        # Refrescar estilos
        self.btn_modo_pantalla.style().unpolish(self.btn_modo_pantalla)
        self.btn_modo_pantalla.style().polish(self.btn_modo_pantalla)
        self.btn_modo_mesa.style().unpolish(self.btn_modo_mesa)
        self.btn_modo_mesa.style().polish(self.btn_modo_mesa)

    def on_smooth_change(self, value):
        if self.camera_thread and self.camera_thread.running:
            self.camera_thread.pending_smoothness = value
            self.log_msg(f"Estabilidad solicitada: {value}")

    def on_sens_change(self, value):
        if self.camera_thread and self.camera_thread.running:
            self.camera_thread.pending_sensitivity = value / 100.0
            self.log_msg(f"Sensibilidad solicitada: {value}%")

    def start_calibration(self):
        if self.detector and self.detector.modo == ModoOperacion.MESA:
            self.detector._iniciar_calibracion()
            self.log_msg("CALIBRACIÓN EN CURSO...")

    def update_video_frame(self, cv_img):
        h, w, ch = cv_img.shape
        bytes_per_line = ch * w
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        q_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
        
        pixmap = QPixmap.fromImage(q_img).scaled(
            self.video_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.video_label.setPixmap(pixmap)

    def update_hud(self, modo, gesto, confianza):
        self.hud_label.setText(f"MODO: {modo} | GESTO: {gesto} | CONFIANZA: {confianza:.2f}")

    def keyPressEvent(self, event):
        """Atajos de teclado de la aplicación."""
        key = event.key()
        if key == Qt.Key_Q or key == Qt.Key_Escape:
            self.close()
        elif key == Qt.Key_M:
            nuevo = "mesa" if self.detector.modo == ModoOperacion.PANTALLA else "pantalla"
            self.set_mode(nuevo)
        elif key == Qt.Key_C:
            self.start_calibration()
        elif key == Qt.Key_R:
            if hasattr(self.detector, '_activar_deteccion_automatica'):
                self.detector._activar_deteccion_automatica()
                self.log_msg("Detección reseteada.")

    def closeEvent(self, event):
        if self.camera_thread:
            self.camera_thread.stop()
        event.accept()

def main():
    import sys
    # Evitar warnings de Wayland/X11 en linux, y asegurar visual nativo
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = GestureControlWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    from PyQt5.QtCore import QTimer
    main()
