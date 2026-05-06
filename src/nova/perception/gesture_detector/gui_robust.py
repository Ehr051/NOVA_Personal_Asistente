import cv2
import numpy as np
import time
import sys
import logging

# Añadir directorio actual al path
sys.path.append(".")
try:
    from detectorGestos import DetectorGestos, ModoOperacion, TipoGesto
except ImportError as e:
    print(f"Error al importar DetectorGestos: {e}")
    sys.exit(1)

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GUI_Robust")

class Boton:
    def __init__(self, x, y, w, h, texto, color_base, color_hover, accion):
        self.rect = (x, y, w, h)
        self.texto = texto
        self.color_base = color_base
        self.color_hover = color_hover
        self.accion = accion
        self.hover = False
        
    def dibujar(self, frame):
        x, y, w, h = self.rect
        color = self.color_hover if self.hover else self.color_base
        
        # Sombra
        cv2.rectangle(frame, (x+2, y+2), (x+w+2, y+h+2), (0, 0, 0), -1)
        # Botón
        cv2.rectangle(frame, (x, y), (x+w, y+h), color, -1)
        # Borde
        cv2.rectangle(frame, (x, y), (x+w, y+h), (200, 200, 200), 1)
        
        # Texto centrado
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.6
        thickness = 2
        (text_w, text_h), _ = cv2.getTextSize(self.texto, font, scale, thickness)
        text_x = x + (w - text_w) // 2
        text_y = y + (h + text_h) // 2
        
        cv2.putText(frame, self.texto, (text_x, text_y), font, scale, (255, 255, 255), thickness)

    def punto_dentro(self, px, py):
        x, y, w, h = self.rect
        return x <= px <= x+w and y <= py <= y+h

class InterfazOpencv:
    def __init__(self):
        self.window_name = "Centro de Comando Tactico (Modo Robusto)"
        self.detector = DetectorGestos(modo="pantalla")
        # DESACTIVAR la interfaz antigua para que no se vea doble
        self.detector.mostrar_interfaz = False 
        
        self.mostrar_ui = True # Estado de visibilidad de la interfaz
        self.boton_clickeado = None
        
        # Estado
        self.ancho_total = 1280
        self.alto_total = 720
        self.panel_ancho = 300
        
        # Botones
        self.botones = [
            Boton(self.ancho_total - 280, 50, 260, 50, "MODO PANTALLA", (100, 100, 100), (150, 150, 150), 
                  lambda: self.set_mode("pantalla")),
            Boton(self.ancho_total - 280, 110, 260, 50, "MODO MESA", (100, 100, 100), (150, 150, 150), 
                  lambda: self.set_mode("mesa")),
            Boton(self.ancho_total - 280, 200, 260, 50, "CALIBRAR MESA", (0, 100, 200), (0, 150, 255), 
                  lambda: self.start_calibration()),
            Boton(self.ancho_total - 280, 650, 260, 50, "SALIR (Q)", (0, 0, 150), (0, 0, 200), 
                  lambda: self.close())
        ]
        
        # Trackbars se inicializan después de crear la ventana
        
    def set_mode(self, mode):
        if mode == "mesa":
            self.detector.modo = ModoOperacion.MESA
            self.detector._cambiar_modo()
            print("Switched to MESA mode")
        else:
            self.detector.modo = ModoOperacion.PANTALLA
            self.detector._cambiar_modo()
            print("Switched to PANTALLA mode")

    def start_calibration(self):
        if self.detector.modo == ModoOperacion.MESA:
            self.detector._iniciar_calibracion()
        else:
            print("¡Debes estar en Modo Mesa para calibrar!")

    def close(self):
        self.running = False

    def on_mouse(self, event, x, y, flags, param):
        if event == cv2.EVENT_MOUSEMOVE:
            for btn in self.botones:
                btn.hover = btn.punto_dentro(x, y)
                
        elif event == cv2.EVENT_LBUTTONDOWN:
            for btn in self.botones:
                if btn.punto_dentro(x, y):
                    btn.accion()
                    
    def on_trackbar_smooth(self, val):
        val = max(1, val)
        self.detector.configuracion.suavizado_movimiento = val
        self.detector.suavizado = val
        
    def on_trackbar_sens(self, val):
        # Mapear 1-100 a 0.0-1.0
        conf = val / 100.0
        conf = max(0.1, min(1.0, conf))
        self.detector.actualizar_sensibilidad(conf)

    def run(self):
        self.cap = cv2.VideoCapture(0)
        self.running = True
        
        cv2.namedWindow(self.window_name)
        cv2.setMouseCallback(self.window_name, self.on_mouse)
        
        # Crear Trackbars
        cv2.createTrackbar("Suavizado", self.window_name, 5, 20, self.on_trackbar_smooth)
        cv2.createTrackbar("Sensibilidad %", self.window_name, 70, 100, self.on_trackbar_sens)
        
        while self.running and self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret:
                break
            
            frame = cv2.flip(frame, 1)
            
            # Procesar detección
            frame, info = self.detector.procesar_frame(frame)
            
            # Crear canvas más grande para incluir panel
            h, w = frame.shape[:2]
            
            # Resize frame to fit in main area maintaining aspect ratio
            target_w = self.ancho_total - self.panel_ancho
            scale = target_w / w
            new_w = int(w * scale)
            new_h = int(h * scale)
            frame_resized = cv2.resize(frame, (new_w, new_h))
            
            # Canvas negro
            canvas = np.zeros((self.alto_total, self.ancho_total, 3), dtype=np.uint8)
            
            # Pegar frame de video centrado verticalmente
            y_offset = (self.alto_total - new_h) // 2
            canvas[y_offset:y_offset+new_h, 0:new_w] = frame_resized
            
            # --- Panel Lateral (Solo si UI visible) ---
            if self.mostrar_ui:
                panel_x = self.ancho_total - self.panel_ancho
                cv2.rectangle(canvas, (panel_x, 0), (self.ancho_total, self.alto_total), (30, 30, 30), -1)
                cv2.line(canvas, (panel_x, 0), (panel_x, self.alto_total), (100, 100, 100), 2)
                
                # Título
                cv2.putText(canvas, "COMANDO TACTICO", (panel_x + 20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
                # Estado actual sobre el panel
                cv2.putText(canvas, f"Modo: {self.detector.modo.value.upper()}", (panel_x + 20, 300), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 200), 1)
                
                gesto_txt = info.gesto.value.replace('_', ' ').upper()
                cv2.putText(canvas, f"Gesto: {gesto_txt}", (panel_x + 20, 330), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 100), 1)
                
                cv2.putText(canvas, f"Tracking: {info.confianza:.2f}", (panel_x + 20, 360), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

                # Dibujar botones
                for btn in self.botones:
                    # Actualizar estado visual de botones de modo
                    if "PANTALLA" in btn.texto and self.detector.modo == ModoOperacion.PANTALLA:
                        btn.color_base = (0, 100, 0)
                    elif "PANTALLA" in btn.texto:
                        btn.color_base = (50, 50, 50)
                        
                    if "MESA" in btn.texto and "CALIBRAR" not in btn.texto and self.detector.modo == ModoOperacion.MESA:
                        btn.color_base = (0, 100, 0)
                    elif "MESA" in btn.texto and "CALIBRAR" not in btn.texto:
                        btn.color_base = (50, 50, 50)
                    
                    # Desactivar botón calibrar si no está en mesa
                    if "CALIBRAR" in btn.texto:
                        if self.detector.modo != ModoOperacion.MESA:
                            btn.color_base = (30, 30, 30)
                            btn.texto = "(Requiere Modo Mesa)"
                        else:
                            btn.color_base = (0, 100, 200)
                            btn.texto = "CALIBRAR MESA"

                    btn.dibujar(canvas)
            else:
                # Indicador discreto cuando UI oculta
                cv2.putText(canvas, "UI OCULTA (Presiona 'V')", (self.ancho_total - 250, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 100, 100), 2)

            # Mostrar
            cv2.imshow(self.window_name, canvas)
            
            key = cv2.waitKey(1) & 0xFF
            
            # --- ATAJOS DE TECLADO ---
            if key == ord('q') or key == 27: # ESC
                break
            elif key == ord('v'): # Toggle UI
                self.mostrar_ui = not self.mostrar_ui
                # Sincronizar con el detector por si acaso
                self.detector.mostrar_interfaz = False 
                print(f"UI Visible: {self.mostrar_ui}")
            elif key == ord('m'): # Cambiar Modo
                nuevo_modo = "mesa" if self.detector.modo == ModoOperacion.PANTALLA else "pantalla"
                self.set_mode(nuevo_modo)
            elif key == ord('c'): # Calibrar (solo mesa)
                self.start_calibration()
            elif key == ord('r'): # Reset
                self.detector._activar_deteccion_automatica()
                
        self.cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    app = InterfazOpencv()
    app.run()
