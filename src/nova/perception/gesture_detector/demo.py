#!/usr/bin/env python3
"""
Demo Rápido - Sistema de Control por Gestos
==========================================

Una demostración rápida del sistema con configuración optimizada
para mostrar las capacidades principales en pocos minutos.
"""

# Imports con manejo de errores para linting
try:
    import cv2  # type: ignore
except ImportError:
    cv2 = None

try:
    import mediapipe as mp  # type: ignore
except ImportError:
    mp = None

try:
    import numpy as np  # type: ignore
except ImportError:
    np = None

import time
import sys

class DemoGestos:
    def __init__(self):
        """Inicializa el demo con configuración simplificada"""
        print("🚀 Iniciando Demo del Sistema de Control por Gestos")
        print("=" * 50)
        
        # Configuración optimizada para demo
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.8,
            min_tracking_confidence=0.7
        )
        self.mp_drawing = mp.solutions.drawing_utils
        
        # Variables para demo
        self.gestos_detectados = []
        self.tiempo_inicio = time.time()
        
    def detectar_gesto_simple(self, landmarks, ancho, altura):
        """Detección simplificada de gestos para demo"""
        puntos = []
        for landmark in landmarks.landmark:
            x, y = int(landmark.x * ancho), int(landmark.y * altura)
            puntos.append((x, y))
        
        # Puntos clave
        pulgar_punta = puntos[4]
        indice_punta = puntos[8]
        medio_punta = puntos[12]
        
        # Distancias
        distancia_pulgar_indice = np.sqrt(
            (pulgar_punta[0] - indice_punta[0])**2 + 
            (pulgar_punta[1] - indice_punta[1])**2
        )
        
        distancia_pulgar_medio = np.sqrt(
            (pulgar_punta[0] - medio_punta[0])**2 + 
            (pulgar_punta[1] - medio_punta[1])**2
        )
        
        # Detección de gestos
        if distancia_pulgar_indice < 30:
            return "👌 Click Izquierdo", (255, 0, 0)
        elif distancia_pulgar_medio < 30:
            return "🤟 Click Derecho", (0, 0, 255)
        else:
            return "✋ Cursor", (0, 255, 0)
    
    def procesar_frame(self, frame):
        """Procesa cada frame para el demo"""
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(frame_rgb)
        
        altura, ancho = frame.shape[:2]
        
        # Información de demo en pantalla
        tiempo_transcurrido = int(time.time() - self.tiempo_inicio)
        cv2.putText(frame, f"DEMO - Tiempo: {tiempo_transcurrido}s", 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        cv2.putText(frame, "Gestos disponibles:", 
                   (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, "• Pulgar + Indice = Click Izquierdo", 
                   (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(frame, "• Pulgar + Medio = Click Derecho", 
                   (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(frame, "• Mano abierta = Cursor", 
                   (10, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        cv2.putText(frame, "Presiona 'q' para salir", 
                   (10, altura - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        
        if results.multi_hand_landmarks:
            for hand_idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
                # Dibujar landmarks
                self.mp_drawing.draw_landmarks(
                    frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)
                
                # Detectar gesto
                gesto, color = self.detectar_gesto_simple(hand_landmarks, ancho, altura)
                
                # Mostrar gesto detectado
                cv2.putText(frame, f"Mano {hand_idx + 1}: {gesto}", 
                           (10, 180 + hand_idx * 30), cv2.FONT_HERSHEY_SIMPLEX, 
                           0.8, color, 2)
                
                # Agregar a historial
                if gesto not in ["✋ Cursor"]:  # No registrar cursor constante
                    timestamp = time.time() - self.tiempo_inicio
                    self.gestos_detectados.append((timestamp, gesto))
        
        # Mostrar estadísticas
        gestos_unicos = len(set([g[1] for g in self.gestos_detectados]))
        cv2.putText(frame, f"Gestos únicos detectados: {gestos_unicos}", 
                   (ancho - 400, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        
        return frame
    
    def ejecutar_demo(self):
        """Ejecuta la demostración"""
        print("📷 Iniciando cámara...")
        cap = cv2.VideoCapture(0)
        
        if not cap.isOpened():
            print("❌ No se pudo acceder a la cámara")
            return False
        
        print("✅ Cámara iniciada correctamente")
        print("\n📋 Instrucciones:")
        print("   • Muestra tu mano frente a la cámara")
        print("   • Prueba diferentes gestos")
        print("   • Presiona 'q' para salir")
        print("\n🎬 ¡Demo iniciado!")
        
        cv2.namedWindow('Demo - Control por Gestos', cv2.WINDOW_AUTOSIZE)
        
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    print("❌ Error capturando frame")
                    break
                
                # Voltear horizontalmente para mejor experiencia
                frame = cv2.flip(frame, 1)
                
                # Procesar frame
                frame_procesado = self.procesar_frame(frame)
                
                # Mostrar resultado
                cv2.imshow('Demo - Control por Gestos', frame_procesado)
                
                # Salir con 'q'
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                    
        except KeyboardInterrupt:
            print("\n⚠️ Demo interrumpido por el usuario")
        
        finally:
            cap.release()
            cv2.destroyAllWindows()
            self.mostrar_resumen()
        
        return True
    
    def mostrar_resumen(self):
        """Muestra un resumen del demo"""
        print("\n" + "=" * 50)
        print("    RESUMEN DEL DEMO")
        print("=" * 50)
        
        tiempo_total = time.time() - self.tiempo_inicio
        print(f"⏱️  Duración del demo: {tiempo_total:.1f} segundos")
        print(f"🎯 Total de gestos detectados: {len(self.gestos_detectados)}")
        
        if self.gestos_detectados:
            gestos_unicos = set([g[1] for g in self.gestos_detectados])
            print(f"🎮 Gestos únicos probados: {len(gestos_unicos)}")
            for gesto in gestos_unicos:
                print(f"   • {gesto}")
        
        print("\n🎉 ¡Demo completado!")
        print("📖 Para usar el sistema completo, ejecuta:")
        print("   python control_gestos.py")
        print("   o usa los launchers:")
        print("   ./launch_macos.sh (macOS)")
        print("   launch_windows.bat (Windows)")

def main():
    """Función principal del demo"""
    try:
        demo = DemoGestos()
        demo.ejecutar_demo()
    except ImportError as e:
        print("❌ Error importando dependencias:")
        print(f"   {e}")
        print("\n💡 Solución:")
        print("   1. Ejecuta: python instalar.py")
        print("   2. O instala manualmente: pip install opencv-python mediapipe numpy")
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        return False
    
    return True

if __name__ == "__main__":
    main()
