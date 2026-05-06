import customtkinter as ctk
import cv2
import threading
from PIL import Image, ImageTk
import sys
import logging
import time
import numpy as np

# Añadir directorio actual al path para importar módulos locales
sys.path.append(".")
try:
    from detectorGestos import DetectorGestos, ModoOperacion
except ImportError as e:
    print(f"Error al importar DetectorGestos: {e}")
    sys.exit(1)

# Configuración de CustomTkinter
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class TacticalCommandCenter(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("Sistema de Control Táctico de Gestos v3.0")
        self.geometry("1200x800")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Grid layout
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # --- Sidebar (Controles) ---
        self.sidebar_frame = ctk.CTkFrame(self, width=280, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(9, weight=1)
        
        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="COMANDO TÁCTICO", font=ctk.CTkFont(size=22, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))
        
        # Botão Principal
        self.start_button = ctk.CTkButton(self.sidebar_frame, text="INICIAR SISTEMA", fg_color="#2ecc71", hover_color="#27ae60", command=self.toggle_system, font=ctk.CTkFont(weight="bold"))
        self.start_button.grid(row=1, column=0, padx=20, pady=15)
        
        # Modos
        self.mode_label = ctk.CTkLabel(self.sidebar_frame, text="Modo de Operación:", anchor="w", font=ctk.CTkFont(weight="bold"))
        self.mode_label.grid(row=2, column=0, padx=20, pady=(10, 0), sticky="w")
        
        self.mode_option = ctk.CTkOptionMenu(self.sidebar_frame, values=["Pantalla (Desktop)", "Mesa de Arena (Proyección)"], command=self.change_mode)
        self.mode_option.grid(row=3, column=0, padx=20, pady=5)
        
        # Controles de Precisão
        self.precision_label = ctk.CTkLabel(self.sidebar_frame, text="Estabilidad (Suavizado):", anchor="w", font=ctk.CTkFont(weight="bold"))
        self.precision_label.grid(row=4, column=0, padx=20, pady=(15, 0), sticky="w")
        
        self.smooth_slider = ctk.CTkSlider(self.sidebar_frame, from_=1, to=15, number_of_steps=14, command=self.update_smoothing)
        self.smooth_slider.grid(row=5, column=0, padx=20, pady=5)
        self.smooth_slider.set(5)
        
        self.sens_label = ctk.CTkLabel(self.sidebar_frame, text="Sensibilidad Detección:", anchor="w", font=ctk.CTkFont(weight="bold"))
        self.sens_label.grid(row=6, column=0, padx=20, pady=(15, 0), sticky="w")
        
        self.sens_slider = ctk.CTkSlider(self.sidebar_frame, from_=0.5, to=1.0, command=self.update_sensitivity)
        self.sens_slider.grid(row=7, column=0, padx=20, pady=5)
        self.sens_slider.set(0.7)
        
        # Botão de Calibração (Só ativo em modo mesa)
        self.calib_button = ctk.CTkButton(self.sidebar_frame, text="CALIBRAR MESA", fg_color="#e67e22", hover_color="#d35400", command=self.start_calibration, state="disabled")
        self.calib_button.grid(row=8, column=0, padx=20, pady=20)
        
        # Console de Estado
        self.console_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.console_frame.grid(row=9, column=0, padx=20, pady=20, sticky="nsew")
        self.console_log = ctk.CTkTextbox(self.console_frame, height=150, font=ctk.CTkFont(family="Courier", size=11))
        self.console_log.pack(fill="both", expand=True)
        self.log_message("Sistema de Comando Táctico listo.")
        self.log_message("Esperando inicialización...")
        
        # --- Área Principal (Preview) ---
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="#000000")
        self.main_frame.grid(row=0, column=1, sticky="nsew")
        self.main_frame.grid_rowconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)
        
        # Container para o vídeo (centralizado)
        self.video_container = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.video_container.grid(row=0, column=0, sticky="ns")
        
        self.preview_label = ctk.CTkLabel(self.video_container, text="CÁMARA INACTIVA\n\nPresione 'INICIAR SISTEMA'", fg_color="#1a1a1a", corner_radius=10, font=ctk.CTkFont(size=16))
        self.preview_label.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Status Bar Overlay
        self.status_bar = ctk.CTkLabel(self.main_frame, text="ESTADO: EN ESPERA", anchor="w", font=ctk.CTkFont(size=12, family="Courier", weight="bold"), bg_color="#1a1a1a", text_color="#00ff00")
        self.status_bar.grid(row=1, column=0, sticky="ew", padx=0, pady=0)

        # Estado interno
        self.is_running = False
        self.thread_active = False
        self.detector = None
        self.cap = None
        self.frame_scan_id = None
        
        # Inicializar detector en segundo plano
        try:
            self.detector = DetectorGestos(modo="pantalla")
            # Configurar para no mostrar interfaz interna del detector (nosotros dibujaremos o mostraremos el frame limpio)
            self.detector.mostrar_interfaz = True 
        except Exception as e:
            self.log_message(f"Error fatal iniciando detector: {e}")

    def log_message(self, msg):
        self.console_log.insert("end", f"> {msg}\n")
        self.console_log.see("end")

    def toggle_system(self):
        if not self.is_running:
            self.start_system()
        else:
            self.stop_system()

    def start_system(self):
        if self.detector is None:
            self.detector = DetectorGestos()
        
        self.is_running = True
        self.thread_active = True
        self.start_button.configure(text="DETENER SISTEMA", fg_color="#e74c3c", hover_color="#c0392b")
        self.log_message("Iniciando cámara y detección...")
        
        # Iniciar thread de vídeo
        self.video_thread = threading.Thread(target=self.video_loop, daemon=True)
        self.video_thread.start()
        
    def stop_system(self):
        self.is_running = False
        self.thread_active = False
        self.start_button.configure(text="INICIAR SISTEMA", fg_color="#2ecc71", hover_color="#27ae60")
        self.preview_label.configure(image=None, text="SISTEMA DETENIDO") 
        self.log_message("Sistema detenido.")

    def change_mode(self, choice):
        if self.detector:
            if "Mesa" in choice:
                self.detector.modo = ModoOperacion.MESA
                self.detector._cambiar_modo() # Para activar lógica interna
                self.calib_button.configure(state="normal")
                self.log_message("Modo MESA activado. Calibración habilitada.")
            else:
                self.detector.modo = ModoOperacion.PANTALLA
                self.detector._cambiar_modo()
                self.calib_button.configure(state="disabled")
                self.log_message("Modo PANTALLA activado.")

    def update_smoothing(self, value):
        if self.detector:
            self.detector.configuracion.suavizado_movimiento = int(value)
            self.detector.suavizado = int(value)
            self.log_message(f"Suavizado ajustado a: {int(value)}")

    def update_sensitivity(self, value):
        if self.detector:
            # Usar el nuevo método para actualizar sensibilidad dinámicamente
            self.detector.actualizar_sensibilidad(float(value))
            self.log_message(f"Sensibilidad actualizada a: {value:.2f}")

    def start_calibration(self):
        if self.detector and self.detector.modo == ModoOperacion.MESA:
            self.detector._iniciar_calibracion()
            self.log_message("INICIANDO CALIBRACIÓN MANUAL")
            self.log_message("Sigue las instrucciones en pantalla")

    def video_loop(self):
        self.cap = cv2.VideoCapture(0)
        
        if not self.cap.isOpened():
            self.is_main_thread_calling(self.log_message, "Error: No se puede acceder a la cámara")
            self.is_running = False
            return

        while self.thread_active:
            ret, frame = self.cap.read()
            if not ret:
                break
            
            # Espejar para sensación natural
            frame = cv2.flip(frame, 1)
            
            # Procesar con el detector
            if self.detector:
                frame, info = self.detector.procesar_frame(frame)
                
                # Actualizar status bar con info del gesto
                gesto_txt = info.gesto.value.upper() if info.gesto else "NINGUNO"
                self.status_bar.configure(text=f"ESTADO: {gesto_txt} | Confianza: {info.confianza:.2f}")

            # Convertir para mostrar en Tkinter
            # Reducir tamaño para mejor rendimiento en GUI
            h, w, _ = frame.shape
            # Mantener aspect ratio
            display_h = 600
            display_w = int(w * (display_h / h))
            frame_resized = cv2.resize(frame, (display_w, display_h))
            
            frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
            img_pil = Image.fromarray(frame_rgb)
            img_tk = ImageTk.PhotoImage(image=img_pil)
            
            # Actualizar GUI en la thread principal
            self.preview_label.configure(image=img_tk, text="")
            self.preview_label.image = img_tk  # Mantener referencia
            
        self.cap.release()

    def is_main_thread_calling(self, func, *args):
        # Helper para llamar func en la main thread si se necesita (Tkinter no es thread-safe)
        # En este caso simplificado esperamos que la GUI aguante updates directos de imagen
        # pero textos es bueno cuidar. CustomTkinter maneja bien esto generalmente.
        func(*args)

    def on_close(self):
        self.stop_system()
        self.destroy()
        sys.exit(0)

if __name__ == "__main__":
    app = TacticalCommandCenter()
    app.mainloop()
