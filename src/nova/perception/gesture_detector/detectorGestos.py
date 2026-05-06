#!/usr/bin/env python3
"""
Sistema Unificado de Control por Gestos - Versión Definitiva
===========================================================

Combina la arquitectura moderna de DetectorGestosOptimizado.py 
con todas las características avanzadas de control_gestos.py

Características principales:
- Arquitectura moderna con dataclasses y enums
- Control de cursor completo con gestos de manos
- Doble click automático
- Interfaz compacta y configurable
- Calibración automática mejorada  
- Dos modos: pantalla y mesa (con calibración)
- Logging avanzado y configuración optimizada

Autor: Sistema de Control por Gestos
Versión: 3.0 (Definitiva)
"""

import cv2
import mediapipe as mp
import numpy as np
import time
import pyautogui
import sys
import os
import json
import logging
import argparse
from pathlib import Path
from typing import Tuple, Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('detector_gestos.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configurar pyautogui para que sea seguro y funcione correctamente
pyautogui.PAUSE = 0.01
pyautogui.FAILSAFE_POINTS = [(0, 0)]  # Solo esquina superior izquierda como punto de seguridad

# ================================
# CLASES Y TIPOS DE DATOS
# ================================

class ModoOperacion(Enum):
    """Modos de operación del sistema"""
    PANTALLA = "pantalla"
    MESA = "mesa"

class TipoGesto(Enum):
    """Tipos de gestos reconocidos"""
    CURSOR = "cursor"
    CLICK_IZQUIERDO = "click_izquierdo"
    DOBLE_CLICK = "doble_click"
    CLICK_DERECHO = "click_derecho"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    NINGUNO = "ninguno"

@dataclass
class ConfiguracionSistema:
    """Configuración del sistema con valores por defecto"""
    # Detección
    min_detection_confidence: float = 0.7
    min_tracking_confidence: float = 0.5
    max_num_hands: int = 2
    
    # Gestos
    distancia_pinza: int = 40
    factor_zoom_in: float = 1.5
    factor_zoom_out: float = 0.7
    suavizado_movimiento: int = 5
    doble_click_ventana: float = 0.5
    tiempo_calibracion: float = 3.0
    
    # Interfaz
    mostrar_por_defecto: bool = True
    color_primario: Tuple[int, int, int] = (0, 255, 0)
    color_secundario: Tuple[int, int, int] = (255, 255, 0)
    color_error: Tuple[int, int, int] = (0, 0, 255)

@dataclass
class InfoGesto:
    """Información sobre un gesto detectado"""
    gesto: TipoGesto
    posicion: Optional[Tuple[int, int]] = None
    confianza: float = 0.0
    metadatos: Dict[str, Any] = None

class DetectorGestos:
    """
    Detector de gestos principal que combina lo mejor de ambas versiones
    """
    
    def __init__(self, modo: str = "pantalla"):
        """
        Inicializa el detector de gestos
        
        Args:
            modo: 'pantalla' para control directo de PC, 'mesa' para proyecciones
        """
        self.modo = ModoOperacion(modo)
        
        # Cargar configuración
        self.config = self._cargar_configuracion()
        
        # Extraer solo los campos válidos para ConfiguracionSistema
        sistema_config = self.config.get('sistema', {})
        config_valida = {
            'min_detection_confidence': self.config.get('deteccion', {}).get('min_detection_confidence', 0.7),
            'min_tracking_confidence': self.config.get('deteccion', {}).get('min_tracking_confidence', 0.5),
            'max_num_hands': self.config.get('deteccion', {}).get('max_num_hands', 2),
            'distancia_pinza': self.config.get('gestos', {}).get('distancia_pinza', 40),
            'factor_zoom_in': self.config.get('gestos', {}).get('factor_zoom_in', 1.5),
            'factor_zoom_out': self.config.get('gestos', {}).get('factor_zoom_out', 0.7),
            'suavizado_movimiento': self.config.get('gestos', {}).get('suavizado_movimiento', 5),
            'doble_click_ventana': self.config.get('gestos', {}).get('doble_click_ventana', 0.5),
            'tiempo_calibracion': self.config.get('gestos', {}).get('tiempo_calibracion', 3.0),
            'mostrar_por_defecto': self.config.get('interfaz', {}).get('mostrar_por_defecto', True)
        }
        self.configuracion = ConfiguracionSistema(**config_valida)
        
        # Inicializar MediaPipe Hands
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=self.configuracion.max_num_hands,
            min_detection_confidence=self.configuracion.min_detection_confidence,
            min_tracking_confidence=self.configuracion.min_tracking_confidence
        )
        self.mp_drawing = mp.solutions.drawing_utils
        
        # Estado de precisión táctica
        self.modo_precision = False
        self.umbral_estabilidad = 2.0  # Píxeles de movimiento mínimo para considerar "intencional" en modo precisión
        self.posicion_estable = (0, 0)
        
        # Obtener tamaño de la pantalla
        self.ancho_pantalla, self.alto_pantalla = pyautogui.size()
        logger.info(f"Resolución de pantalla: {self.ancho_pantalla}x{self.alto_pantalla}")
        
        # Variables de estado para gestos
        self.cursor_x, self.cursor_y = 0, 0
        self.arrastrando = False
        self.boton_presionado = False  # Estado del botón del mouse para arrastre
        
        # Variables para calibración automática de distancia
        self.tamaño_mano_referencia = None  # Tamaño promedio de la mano
        self.factor_distancia = 1.0  # Factor de ajuste basado en distancia
        self.historial_tamaños_mano = []  # Últimos 10 tamaños para promedio
        self.distancia_pinza_adaptativa = self.configuracion.distancia_pinza
        self.ultimo_click_tiempo = 0
        self.click_count = 0
        self.gesto_anterior = TipoGesto.NINGUNO
        self.tiempo_gesto_anterior = time.time()
        
        # Variables para zoom con dos puños
        self.zoom_activo = False
        self.distancia_puños_anterior = 0
        self.zoom_base = 1.0
        self.cooldown_zoom = 0
        
        # Suavizado de movimiento
        self.historial_x = []
        self.historial_y = []
        self.suavizado = self.configuracion.suavizado_movimiento
        
        # Matriz de transformación para mapear coordenadas entre la cámara y proyección
        self.matriz_transformacion = np.eye(3)  # Identidad por defecto
        
        # Variables para calibración mejorada
        self.calibrando = False
        self.puntos_camara = []
        self.puntos_proyeccion = []
        self.esquina_actual = 0
        self.tiempo_en_punto = 0
        self.tiempo_requerido_calibracion = self.configuracion.tiempo_calibracion
        self.punto_calibracion_activo = False
        
        # Variables para confirmación de calibración
        self.esperando_confirmacion = False
        self.confirmacion_opcion = 0  # 0=Confirmar, 1=Recalibrar, 2=Cancelar
        self.mostrar_preview_pantalla = False
        
        # Variables para la interfaz
        self.ultimo_gesto = TipoGesto.NINGUNO
        self.tiempo_gesto = time.time()
        self.mostrar_interfaz = self.configuracion.mostrar_por_defecto
        
        # Variables para doble click
        self.doble_click_ventana = self.configuracion.doble_click_ventana
        
        # Variable para cambio de cámara
        self.cambiar_camara_solicitado = False
        
        # Variable para salir por gesto
        self.salir_solicitado = False
        
        # Cargar calibración existente si está en modo mesa
        if self.modo == ModoOperacion.MESA:
            self._cargar_calibracion()
        
        # Habilitar detección automática de proyección para ambos modos
        self._detectar_proyeccion_automatica = True
        self.area_proyeccion = None  # (x, y, width, height) del área detectada
        self.vertices_proyeccion = None  # Vértices exactos del cuadrilátero detectado
        self.matriz_perspectiva = None  # Matriz de transformación de perspectiva
        self.marcos_sin_deteccion = 0
        
        # Margen de tolerancia alrededor del área (en píxeles)
        # Permite que parte de la mano esté fuera al interactuar con los bordes
        self.MARGEN_AREA = 80  # 80 píxeles de margen alrededor del área
        
        # Variables de confirmación automática
        self.area_pendiente_confirmacion = None
        self.tiempo_deteccion = 0
        self.TIEMPO_CONFIRMACION = 3.0  # 3 segundos para confirmar
        
        logger.info(f"Modo {self.modo.value.upper()} activado - Detección automática de proyección habilitada")
        
        logger.info(f"Detector de gestos inicializado en modo: {self.modo.value}")
    
    def _cargar_configuracion(self) -> Dict[str, Any]:
        """Carga la configuración desde el archivo config.json"""
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
            logger.info("Configuración cargada exitosamente")
            return config
        except FileNotFoundError:
            logger.warning("Archivo config.json no encontrado, usando configuración por defecto")
            return {
                "deteccion": {
                    "min_detection_confidence": 0.7,
                    "min_tracking_confidence": 0.5
                },
                "gestos": {
                    "distancia_pinza": 40,
                    "factor_zoom_in": 1.5,
                    "factor_zoom_out": 0.7,
                    "suavizado_movimiento": 5,
                    "doble_click_ventana": 0.5,
                    "tiempo_calibracion": 3.0
                },
                "interfaz": {
                    "mostrar_por_defecto": True
                },
                "sistema": {}
            }
    
    def actualizar_sensibilidad(self, min_detection_confidence: float, min_tracking_confidence: float = 0.5):
        """
        Actualiza la configuración de detección y reinicia MediaPipe Hands
        
        Args:
            min_detection_confidence: Nueva confianza mínima de detección
            min_tracking_confidence: Nueva confianza mínima de rastreo
        """
        if (self.configuracion.min_detection_confidence == min_detection_confidence and 
            self.configuracion.min_tracking_confidence == min_tracking_confidence):
            return

        logger.info(f"🔄 Actualizando sensibilidad: Det={min_detection_confidence}, Track={min_tracking_confidence}")
        
        self.configuracion.min_detection_confidence = min_detection_confidence
        self.configuracion.min_tracking_confidence = min_tracking_confidence
        
        # Reinicializar MediaPipe con nuevos parámetros
        if hasattr(self, 'hands'):
            self.hands.close()
            
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=self.configuracion.max_num_hands,
            min_detection_confidence=self.configuracion.min_detection_confidence,
            min_tracking_confidence=self.configuracion.min_tracking_confidence
        )
    
    def alternar_interfaz(self):
        """Alterna entre mostrar y ocultar la interfaz"""
        self.mostrar_interfaz = not self.mostrar_interfaz
        estado = "visible" if self.mostrar_interfaz else "oculta"
        logger.info(f"Interfaz {estado}")
    
    def _cambiar_modo(self):
        """Cambia entre modo pantalla y mesa"""
        if self.modo == ModoOperacion.PANTALLA:
            self.modo = ModoOperacion.MESA
            # 🔄 ACTIVAR DETECCIÓN AUTOMÁTICA AL CAMBIAR A MODO MESA
            self._detectar_proyeccion_automatica = True
            self.area_proyeccion = None
            self.marcos_sin_deteccion = 0
            logger.info("✅ Cambiado a modo MESA - Detección automática ACTIVADA")
            logger.info("💡 Usa 'C' para calibración manual si necesitas ajustar")
        else:
            self.modo = ModoOperacion.PANTALLA
            # Resetear calibración al cambiar a pantalla
            self.puntos_camara = []
            self.puntos_proyeccion = []
            # Desactivar detección automática en modo pantalla
            self._detectar_proyeccion_automatica = False
            logger.info("Cambiado a modo PANTALLA (control directo)")
    
    def _activar_deteccion_automatica(self):
        """Activa/reinicia la detección automática de proyección"""
        self._detectar_proyeccion_automatica = True
        self.area_proyeccion = None
        self.marcos_sin_deteccion = 0
        # Limpiar calibración manual previa
        self.puntos_camara = []
        self.puntos_proyeccion = []
        self.matriz_transformacion = np.eye(3)
        self.calibrando = False
        logger.info("🔄 Detección automática REINICIADA - Buscando proyección...")
        logger.info("💡 La detección comenzará en 3 segundos...")
    
    def _cambiar_camara(self):
        """Solicita cambio de cámara al sistema principal"""
        # Esta función será manejada por el sistema principal
        logger.info("Solicitado cambio de cámara")
        self.cambiar_camara_solicitado = True
    
    def _iniciar_calibracion(self):
        """Inicia el proceso de calibración para modo mesa"""
        if self.modo == ModoOperacion.MESA:
            # 🚫 DESACTIVAR DETECCIÓN AUTOMÁTICA PARA CALIBRACIÓN MANUAL
            self._detectar_proyeccion_automatica = False
            self.area_proyeccion = None
            
            self.calibrando = True
            self.puntos_camara = []
            self.puntos_proyeccion = []
            self.esquina_actual = 0
            self.tiempo_en_punto = 0
            self.punto_calibracion_activo = False
            self.posicion_cursor_proyeccion = None
            
            # No definir esquinas fijas - el usuario elegirá libremente
            self.nombres_esquinas = [
                "SUPERIOR IZQUIERDA",
                "SUPERIOR DERECHA", 
                "INFERIOR DERECHA",
                "INFERIOR IZQUIERDA"
            ]
            
            logger.info("=== INICIANDO CALIBRACIÓN ===")
            logger.info("Define las 4 esquinas de tu área de proyección EN ORDEN:")
            logger.info("  PUNTO 1: SUPERIOR IZQUIERDA")
            logger.info("  PUNTO 2: SUPERIOR DERECHA") 
            logger.info("  PUNTO 3: INFERIOR DERECHA")
            logger.info("  PUNTO 4: INFERIOR IZQUIERDA")
            logger.info("")
            logger.info("INSTRUCCIONES:")
            logger.info("- Usa mano cerrada con ÍNDICE EXTENDIDO")
            logger.info("- Mantén el dedo 3 segundos en cada esquina")
            logger.info("- Presiona 'U' para deshacer el último punto")
            logger.info("")
            logger.info(f">>> APUNTA AL PUNTO 1: {self.nombres_esquinas[0]} <<<")
        else:
            logger.warning("La calibración solo está disponible en modo MESA")
    
    def _procesar_calibracion(self, frame: np.ndarray, landmarks):
        """Procesa el estado de calibración cuando está activa"""
        if not self.calibrando or self.esquina_actual >= 4:
            return
        
        altura, ancho = frame.shape[:2]
        
        # Detectar gesto de índice extendido (mano cerrada con índice arriba)
        puntos = []
        for landmark in landmarks.landmark:
            x = int(landmark.x * ancho)
            y = int(landmark.y * altura)
            puntos.append((x, y))
        
        # Verificar si es gesto de índice extendido
        if not self._es_gesto_indice_extendido(puntos):
            # Si no es el gesto correcto, resetear
            if self.punto_calibracion_activo:
                self.punto_calibracion_activo = False
                self.tiempo_en_punto = 0
            return
        
        # Obtener posición del dedo índice
        indice_tip = landmarks.landmark[8]
        x_dedo = int(indice_tip.x * ancho)
        y_dedo = int(indice_tip.y * altura)
        
        # Obtener posición actual del cursor en pantalla para proyección
        cursor_actual = pyautogui.position()
        
        # Dibujar interfaz de calibración
        self._dibujar_interfaz_calibracion(frame, (x_dedo, y_dedo), cursor_actual)
        
        # Dibujar puntos ya calibrados con conexiones
        self._dibujar_puntos_calibrados(frame)
        
        # Si no hay punto activo, iniciar uno nuevo
        if not self.punto_calibracion_activo:
            self.punto_calibracion_activo = True
            self.tiempo_en_punto = time.time()
            self.posicion_cursor_proyeccion = cursor_actual
        
        # Mostrar progreso
        tiempo_transcurrido = time.time() - self.tiempo_en_punto
        progreso = min(tiempo_transcurrido / self.tiempo_requerido_calibracion, 1.0)
        
        # Dibujar barra de progreso
        self._dibujar_progreso_calibracion(frame, (x_dedo, y_dedo), progreso)
        
        # Si se completó el tiempo requerido
        if tiempo_transcurrido >= self.tiempo_requerido_calibracion:
            # Guardar punto de la cámara y punto de proyección
            self.puntos_camara.append((x_dedo, y_dedo))
            self.puntos_proyeccion.append(self.posicion_cursor_proyeccion)
            
            logger.info(f"✓ PUNTO {self.esquina_actual + 1}/4 COMPLETADO: {self.nombres_esquinas[self.esquina_actual]}")
            
            # Avanzar a la siguiente esquina
            self.esquina_actual += 1
            self.punto_calibracion_activo = False
            
            if self.esquina_actual >= 4:
                self._iniciar_confirmacion_calibracion()
            else:
                # Preparar para el siguiente punto
                logger.info(f">>> SIGUIENTE: PUNTO {self.esquina_actual + 1}/4 - {self.nombres_esquinas[self.esquina_actual]} <<<")
                logger.info("CONSEJO: Si el punto anterior no quedó bien, presiona 'U' para deshacerlo")
    
    def _dibujar_puntos_calibrados(self, frame: np.ndarray):
        """Dibuja los puntos ya calibrados y las conexiones entre ellos"""
        if len(self.puntos_camara) < 2:
            return
        
        # Dibujar puntos calibrados
        for i, punto in enumerate(self.puntos_camara):
            cv2.circle(frame, punto, 15, (0, 255, 0), -1)
            cv2.circle(frame, punto, 20, (0, 255, 0), 2)
            cv2.putText(frame, f"{i+1}", (punto[0]-5, punto[1]+5), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.6, (255, 255, 255), 2)
        
        # Dibujar líneas entre puntos consecutivos
        for i in range(len(self.puntos_camara) - 1):
            cv2.line(frame, self.puntos_camara[i], self.puntos_camara[i+1], (0, 255, 0), 2)
        
        # Si tenemos 4 puntos, cerrar el rectángulo
        if len(self.puntos_camara) >= 3:
            cv2.line(frame, self.puntos_camara[0], self.puntos_camara[-1], (0, 255, 0), 2)
            
        # Si tenemos 4 puntos, dibujar el rectángulo completo
        if len(self.puntos_camara) == 4:
            cv2.line(frame, self.puntos_camara[3], self.puntos_camara[0], (0, 255, 0), 2)
    
    def deshacer_ultimo_punto(self):
        """Deshace el último punto calibrado"""
        if len(self.puntos_camara) > 0 and self.calibrando:
            punto_eliminado = self.puntos_camara.pop()
            self.puntos_proyeccion.pop()
            self.esquina_actual -= 1
            self.punto_calibracion_activo = False
            logger.info(f"Punto {self.esquina_actual + 1} eliminado. Reposiciona en: {self.nombres_esquinas[self.esquina_actual]}")
        else:
            logger.warning("No hay puntos para deshacer")
    
    def _es_gesto_indice_extendido(self, puntos) -> bool:
        """Detecta si la mano está haciendo el gesto de índice extendido"""
        try:
            # Puntos clave de la mano
            pulgar_tip = puntos[4]
            pulgar_ip = puntos[3]
            indice_tip = puntos[8]
            indice_pip = puntos[6]
            indice_mcp = puntos[5]
            medio_tip = puntos[12]
            medio_pip = puntos[10]
            anular_tip = puntos[16]
            anular_pip = puntos[14]
            meñique_tip = puntos[20]
            meñique_pip = puntos[18]
            
            # El índice debe estar extendido (tip más alto que pip)
            indice_extendido = indice_tip[1] < indice_pip[1]
            
            # Los otros dedos deben estar doblados (tip más bajo que pip)
            medio_doblado = medio_tip[1] > medio_pip[1]
            anular_doblado = anular_tip[1] > anular_pip[1]
            meñique_doblado = meñique_tip[1] > meñique_pip[1]
            
            return indice_extendido and medio_doblado and anular_doblado and meñique_doblado
            
        except:
            return False
    
    def _es_gesto_seleccion(self, puntos) -> bool:
        """Detecta si la mano está haciendo el gesto de selección (puño cerrado)"""
        try:
            # Puntos clave de la mano
            indice_tip = puntos[8]
            indice_pip = puntos[6]
            medio_tip = puntos[12]
            medio_pip = puntos[10]
            anular_tip = puntos[16]
            anular_pip = puntos[14]
            meñique_tip = puntos[20]
            meñique_pip = puntos[18]
            
            # Todos los dedos deben estar doblados (tip más bajo que pip)
            indice_doblado = indice_tip[1] > indice_pip[1]
            medio_doblado = medio_tip[1] > medio_pip[1]
            anular_doblado = anular_tip[1] > anular_pip[1]
            meñique_doblado = meñique_tip[1] > meñique_pip[1]
            
            return indice_doblado and medio_doblado and anular_doblado and meñique_doblado
            
        except:
            return False
    
    def _dibujar_interfaz_calibracion(self, frame: np.ndarray, pos_dedo: tuple, pos_cursor: tuple):
        """Dibuja la interfaz de calibración mejorada"""
        altura, ancho = frame.shape[:2]
        
        # Panel de información superior
        panel_alto = 100
        cv2.rectangle(frame, (0, 0), (ancho, panel_alto), (0, 0, 0), -1)
        cv2.rectangle(frame, (0, 0), (ancho, panel_alto), (0, 255, 255), 2)
        
        # Título
        titulo = f"CALIBRACION - Punto {self.esquina_actual + 1}/4"
        cv2.putText(frame, titulo, (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        
        # Instrucciones
        esquina_nombre = self.nombres_esquinas[self.esquina_actual]
        instruccion = f"Esquina: {esquina_nombre}"
        cv2.putText(frame, instruccion, (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        
        # Información de posición
        info_pos = f"Cursor PC: {pos_cursor[0]}, {pos_cursor[1]}"
        cv2.putText(frame, info_pos, (20, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        
        # Indicador en posición del dedo
        cv2.circle(frame, pos_dedo, 30, (0, 255, 255), 3)
        cv2.circle(frame, pos_dedo, 20, (0, 255, 255), 2)
        cv2.circle(frame, pos_dedo, 10, (0, 255, 255), 1)
        cv2.circle(frame, pos_dedo, 5, (0, 255, 255), -1)
        
        # Número de esquina
        cv2.putText(frame, f"{self.esquina_actual + 1}", (pos_dedo[0] - 10, pos_dedo[1] + 50), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 255), 3)
    
    def _dibujar_indicador_calibracion(self, frame: np.ndarray, esquina: Tuple[int, int], numero: int):
        """Dibuja el indicador visual para la calibración"""
        x, y = esquina
        
        # Círculo grande de objetivo
        cv2.circle(frame, (x, y), 40, (0, 255, 255), 3)
        cv2.circle(frame, (x, y), 30, (0, 255, 255), 2)
        cv2.circle(frame, (x, y), 20, (0, 255, 255), 1)
        
        # Número de esquina
        cv2.putText(frame, f"{numero + 1}", (x - 10, y + 10), cv2.FONT_HERSHEY_SIMPLEX, 
                   1, (0, 255, 255), 3)
        
        # Instrucciones
        nombres_esquinas = ["Superior Izquierda", "Superior Derecha", "Inferior Derecha", "Inferior Izquierda"]
        instruccion = f"Toca esquina {nombres_esquinas[numero]} y mantén 3 segundos"
        cv2.putText(frame, instruccion, (50, frame.shape[0] - 50), cv2.FONT_HERSHEY_SIMPLEX, 
                   0.8, (0, 255, 255), 2)
    
    def _dibujar_progreso_calibracion(self, frame: np.ndarray, esquina: Tuple[int, int], progreso: float):
        """Dibuja la barra de progreso de calibración"""
        x, y = esquina
        
        # Círculo de progreso
        radio = 50
        angulo = int(360 * progreso)
        
        # Dibujar arco de progreso
        if progreso > 0:
            # Crear puntos para el arco
            puntos = []
            for i in range(0, angulo, 5):
                rad = np.radians(i - 90)  # Empezar desde arriba
                px = int(x + radio * np.cos(rad))
                py = int(y + radio * np.sin(rad))
                puntos.append((px, py))
            
            if len(puntos) > 1:
                for i in range(len(puntos) - 1):
                    cv2.line(frame, puntos[i], puntos[i + 1], (0, 255, 0), 5)
        
        # Texto de progreso
        porcentaje = int(progreso * 100)
        cv2.putText(frame, f"{porcentaje}%", (x - 20, y - 60), cv2.FONT_HERSHEY_SIMPLEX, 
                   0.8, (0, 255, 0), 2)
    
    def _finalizar_calibracion(self):
        """Finaliza el proceso de calibración y calcula la matriz de transformación"""
        if len(self.puntos_camara) >= 4 and len(self.puntos_proyeccion) >= 4:
            # Convertir a arrays numpy
            puntos_src = np.array(self.puntos_camara, dtype=np.float32)
            puntos_dst = np.array(self.puntos_proyeccion, dtype=np.float32)
            
            # Calcular matriz de transformación
            self.matriz_transformacion = cv2.getPerspectiveTransform(puntos_src, puntos_dst)
            
            self.calibrando = False
            logger.info("Calibración completada exitosamente")
            
            # Guardar calibración a archivo
            self._guardar_calibracion()
        else:
            logger.error("Error en calibración: puntos insuficientes")
    
    def _guardar_calibracion(self):
        """Guarda la matriz de calibración a un archivo"""
        try:
            np.save('calibracion_matriz.npy', self.matriz_transformacion)
            logger.info("Matriz de calibración guardada")
        except Exception as e:
            logger.error(f"Error guardando calibración: {e}")
    
    def _cargar_calibracion(self):
        """Carga una calibración previamente guardada"""
        try:
            if Path('calibracion_matriz.npy').exists():
                self.matriz_transformacion = np.load('calibracion_matriz.npy')
                logger.info("Calibración cargada desde archivo")
                return True
        except Exception as e:
            logger.error(f"Error cargando calibración: {e}")
        return False
    
    def _detectar_area_proyeccion(self, frame: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        """
        Detecta automáticamente el área de proyección en la imagen.
        Busca cuadriláteros grandes (rectángulos o trapecios por perspectiva).
        Maneja proyecciones con ángulo (35-45°) y distorsión trapezoidal.
        """
        try:
            # Convertir a escala de grises
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Aplicar filtro gaussiano para suavizar
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            
            # Detectar bordes con Canny
            edges = cv2.Canny(blurred, 50, 150)
            
            # Encontrar contornos
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            if not contours:
                return None
            
            # Buscar el contorno más grande que sea un cuadrilátero
            for contour in sorted(contours, key=cv2.contourArea, reverse=True):
                area = cv2.contourArea(contour)
                
                # Filtrar contornos muy pequeños (menos del 5% de la imagen)
                min_area = (frame.shape[0] * frame.shape[1]) * 0.05
                if area < min_area:
                    continue
                
                # Aproximar el contorno a un polígono
                # Usar epsilon más flexible para capturar formas con perspectiva
                epsilon = 0.02 * cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, epsilon, True)
                
                # Buscar cuadriláteros (4 vértices) - incluye rectángulos Y trapecios
                if len(approx) == 4:
                    # Obtener los 4 vértices del cuadrilátero
                    vertices = approx.reshape(4, 2)
                    
                    # Ordenar vértices: top-left, top-right, bottom-right, bottom-left
                    vertices = self._ordenar_vertices(vertices)
                    
                    # Guardar vértices exactos para transformación de perspectiva
                    self.vertices_proyeccion = vertices
                    
                    # Calcular bounding box para compatibilidad con código existente
                    x, y, w, h = cv2.boundingRect(approx)
                    
                    # Verificar tamaño mínimo
                    if w > 50 and h > 50:
                        # Calcular matriz de transformación de perspectiva
                        self._calcular_matriz_perspectiva(vertices, w, h)
                        
                        logger.info(f"🎯 Cuadrilátero detectado: {w}x{h} en ({x},{y})")
                        logger.info(f"   Vértices: TL{tuple(vertices[0])}, TR{tuple(vertices[1])}, BR{tuple(vertices[2])}, BL{tuple(vertices[3])}")
                        return (x, y, w, h)
                
                # Si no encontramos un cuadrilátero perfecto, buscar aproximaciones
                elif 5 <= len(approx) <= 6:
                    # Intentar con epsilon más agresivo para forzar 4 vértices
                    epsilon = 0.05 * cv2.arcLength(contour, True)
                    approx = cv2.approxPolyDP(contour, epsilon, True)
                    
                    if len(approx) == 4:
                        vertices = approx.reshape(4, 2)
                        vertices = self._ordenar_vertices(vertices)
                        self.vertices_proyeccion = vertices
                        
                        x, y, w, h = cv2.boundingRect(approx)
                        if w > 50 and h > 50:
                            self._calcular_matriz_perspectiva(vertices, w, h)
                            logger.info(f"🎯 Cuadrilátero aproximado detectado: {w}x{h}")
                            return (x, y, w, h)
            
            return None
            
        except Exception as e:
            logger.error(f"Error detectando área de proyección: {e}")
            return None
    
    def _ordenar_vertices(self, vertices: np.ndarray) -> np.ndarray:
        """
        Ordena los 4 vértices de un cuadrilátero en orden:
        [top-left, top-right, bottom-right, bottom-left]
        Esto es crucial para la transformación de perspectiva correcta.
        """
        # Ordenar por suma de coordenadas (x+y)
        # Top-left tendrá la suma más pequeña, bottom-right la más grande
        suma = vertices.sum(axis=1)
        diff = np.diff(vertices, axis=1)
        
        ordenados = np.zeros((4, 2), dtype=np.float32)
        
        # Top-left: suma mínima
        ordenados[0] = vertices[np.argmin(suma)]
        
        # Bottom-right: suma máxima
        ordenados[2] = vertices[np.argmax(suma)]
        
        # Top-right: diferencia (x-y) mínima
        ordenados[1] = vertices[np.argmin(diff)]
        
        # Bottom-left: diferencia (x-y) máxima
        ordenados[3] = vertices[np.argmax(diff)]
        
        return ordenados
    
    def _calcular_matriz_perspectiva(self, vertices: np.ndarray, ancho: int, alto: int):
        """
        Calcula la matriz de transformación de perspectiva para mapear
        el cuadrilátero detectado (con perspectiva/trapecio) a un rectángulo perfecto.
        
        Esto permite que proyecciones con ángulo se manejen correctamente.
        """
        # Definir los puntos destino: un rectángulo perfecto
        puntos_destino = np.array([
            [0, 0],                    # Top-left
            [ancho - 1, 0],            # Top-right
            [ancho - 1, alto - 1],     # Bottom-right
            [0, alto - 1]              # Bottom-left
        ], dtype=np.float32)
        
        # Calcular matriz de transformación
        self.matriz_perspectiva = cv2.getPerspectiveTransform(
            vertices.astype(np.float32), 
            puntos_destino
        )
        
        logger.debug(f"✓ Matriz de perspectiva calculada para corrección de ángulo")
    
    def _aplicar_transformacion_perspectiva(self, x: int, y: int) -> Tuple[int, int]:
        """
        Aplica la transformación de perspectiva a un punto (x, y).
        Convierte coordenadas del trapecio/cuadrilátero con perspectiva
        a coordenadas del rectángulo normalizado.
        """
        if self.matriz_perspectiva is None:
            return x, y
        
        # Convertir punto a formato homogéneo
        punto = np.array([[[x, y]]], dtype=np.float32)
        
        # Aplicar transformación
        punto_transformado = cv2.perspectiveTransform(punto, self.matriz_perspectiva)
        
        return int(punto_transformado[0][0][0]), int(punto_transformado[0][0][1])
    
    def _dibujar_area_proyeccion(self, frame: np.ndarray):
        """Dibuja el área de proyección detectada (cuadrilátero real + margen de tolerancia)"""
        if hasattr(self, 'area_proyeccion') and self.area_proyeccion:
            x, y, w, h = self.area_proyeccion
            margen = getattr(self, 'MARGEN_AREA', 80)
            
            # Si tenemos los vértices exactos del cuadrilátero, dibujarlos
            if hasattr(self, 'vertices_proyeccion') and self.vertices_proyeccion is not None:
                vertices = self.vertices_proyeccion.astype(np.int32)
                
                # Dibujar el cuadrilátero real (trapecio si hay perspectiva) en verde brillante
                cv2.polylines(frame, [vertices], isClosed=True, color=(0, 255, 0), thickness=3)
                
                # Dibujar los vértices con círculos y etiquetas
                labels = ['TL', 'TR', 'BR', 'BL']
                colors = [(0, 255, 255), (255, 0, 255), (255, 255, 0), (255, 128, 0)]
                for i, (punto, label, color) in enumerate(zip(vertices, labels, colors)):
                    cv2.circle(frame, tuple(punto), 8, color, -1)
                    cv2.putText(frame, label, tuple(punto + 10), 
                              cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                
                # Información sobre corrección de perspectiva
                if hasattr(self, 'matriz_perspectiva') and self.matriz_perspectiva is not None:
                    cv2.putText(frame, "PERSPECTIVA CORREGIDA", (x, y - 35), 
                              cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
            else:
                # Fallback: dibujar rectángulo simple
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 3)
                
                # Esquinas
                cv2.circle(frame, (x, y), 8, (0, 255, 0), -1)
                cv2.circle(frame, (x + w, y), 8, (0, 255, 0), -1)
                cv2.circle(frame, (x + w, y + h), 8, (0, 255, 0), -1)
                cv2.circle(frame, (x, y + h), 8, (0, 255, 0), -1)
            
            # Dibujar zona de margen (bounding box expandido)
            x_margen = max(0, x - margen)
            y_margen = max(0, y - margen)
            w_margen = min(frame.shape[1] - x_margen, w + 2 * margen)
            h_margen = min(frame.shape[0] - y_margen, h + 2 * margen)
            
            overlay = frame.copy()
            cv2.rectangle(overlay, (x_margen, y_margen), 
                         (x_margen + w_margen, y_margen + h_margen), 
                         (0, 200, 0), 2)
            cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)
            
            # Texto informativo
            cv2.putText(frame, f"AREA PROYECCION (Margen: {margen}px)", (x, y - 10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    
    def _punto_dentro_proyeccion(self, x: int, y: int) -> bool:
        """Verifica si un punto está dentro del área de proyección detectada (con margen)"""
        if not hasattr(self, 'area_proyeccion') or not self.area_proyeccion:
            return True  # Si no hay área definida, permitir todos los puntos
        
        px, py, pw, ph = self.area_proyeccion
        
        # Aplicar margen de tolerancia (expandir el área)
        margen = getattr(self, 'MARGEN_AREA', 80)
        x_min = px - margen
        y_min = py - margen
        x_max = px + pw + margen
        y_max = py + ph + margen
        
        return x_min <= x <= x_max and y_min <= y <= y_max
    
    def _mapear_coordenadas_proyeccion(self, x: int, y: int) -> Tuple[int, int]:
        """
        Mapea coordenadas dentro del área de proyección a coordenadas de pantalla.
        Si hay transformación de perspectiva, la aplica primero para corregir distorsión.
        """
        if not hasattr(self, 'area_proyeccion') or not self.area_proyeccion:
            return x, y
        
        px, py, pw, ph = self.area_proyeccion
        
        # Si tenemos transformación de perspectiva, aplicarla primero
        if hasattr(self, 'matriz_perspectiva') and self.matriz_perspectiva is not None:
            # Transformar el punto para corregir perspectiva
            # Esto convierte coordenadas del trapecio a coordenadas rectangulares
            x_relativo = x - px
            y_relativo = y - py
            x_corregido, y_corregido = self._aplicar_transformacion_perspectiva(x_relativo, y_relativo)
            
            # Normalizar usando las dimensiones corregidas
            norm_x = x_corregido / pw if pw > 0 else 0
            norm_y = y_corregido / ph if ph > 0 else 0
        else:
            # Sin corrección de perspectiva, mapeo directo
            norm_x = (x - px) / pw if pw > 0 else 0
            norm_y = (y - py) / ph if ph > 0 else 0
        
        # Limitar a rango válido
        norm_x = max(0.0, min(1.0, norm_x))
        norm_y = max(0.0, min(1.0, norm_y))
        
        # Mapear a coordenadas de pantalla
        screen_x = int(norm_x * pyautogui.size().width)
        screen_y = int(norm_y * pyautogui.size().height)
        
        return screen_x, screen_y
    
    def _configurar_transformacion_automatica(self):
        """Configura la matriz de transformación automáticamente basada en el área detectada"""
        if not hasattr(self, 'area_proyeccion') or not self.area_proyeccion:
            return
        
        try:
            x, y, w, h = self.area_proyeccion
            
            # Definir puntos de la cámara (área detectada)
            self.puntos_camara = [
                (x, y),          # Superior izquierda
                (x + w, y),      # Superior derecha  
                (x + w, y + h),  # Inferior derecha
                (x, y + h)       # Inferior izquierda
            ]
            
            # Definir puntos de proyección (pantalla completa)
            screen_width, screen_height = pyautogui.size()
            self.puntos_proyeccion = [
                (0, 0),                              # Superior izquierda
                (screen_width, 0),                   # Superior derecha
                (screen_width, screen_height),       # Inferior derecha
                (0, screen_height)                   # Inferior izquierda
            ]
            
            # Calcular matriz de transformación
            self._calcular_matriz_transformacion()
            
            logger.info("✅ Transformación automática configurada para área de proyección")
            
        except Exception as e:
            logger.error(f"Error configurando transformación automática: {e}")
    
    def _calcular_matriz_transformacion(self):
        """Calcula la matriz de transformación de perspectiva para mapeo de coordenadas"""
        try:
            if len(self.puntos_camara) >= 4 and len(self.puntos_proyeccion) >= 4:
                # Convertir a arrays numpy
                puntos_src = np.array(self.puntos_camara[:4], dtype=np.float32)
                puntos_dst = np.array(self.puntos_proyeccion[:4], dtype=np.float32)
                
                # Calcular matriz de transformación de perspectiva
                self.matriz_transformacion = cv2.getPerspectiveTransform(puntos_src, puntos_dst)
                logger.debug("✅ Matriz de transformación calculada correctamente")
            else:
                logger.warning(f"Puntos insuficientes para calcular matriz: {len(self.puntos_camara)} cámara, {len(self.puntos_proyeccion)} proyección")
        except Exception as e:
            logger.error(f"Error calculando matriz de transformación: {e}")
            self.matriz_transformacion = np.eye(3)  # Matriz identidad como fallback
    
    def _calcular_tamaño_mano(self, landmarks, frame_shape) -> float:
        """Calcula el tamaño de la mano basado en la distancia entre puntos clave (LEGACY - mantener por compatibilidad)"""
        try:
            altura, ancho = frame_shape[:2]
            
            # Convertir landmarks a coordenadas
            puntos = []
            for landmark in landmarks.landmark:
                x = int(landmark.x * ancho)
                y = int(landmark.y * altura)
                puntos.append((x, y))
            
            # Calcular distancia entre muñeca y dedo medio
            muneca = puntos[0]  # Wrist
            medio_tip = puntos[12]  # Middle finger tip
            
            distancia = np.sqrt((muneca[0] - medio_tip[0])**2 + (muneca[1] - medio_tip[1])**2)
            return distancia
            
        except Exception as e:
            logger.error(f"Error calculando tamaño de mano: {e}")
            return 100.0  # Valor por defecto
    
    def _calcular_distancia_3d_mano(self, landmarks) -> float:
        """
        Calcula la distancia estimada de la mano a la cámara usando coordenadas Z de MediaPipe.
        
        MediaPipe proporciona landmark.z que representa la profundidad relativa:
        - Valores negativos = más cerca de la cámara
        - Valores positivos = más lejos de la cámara
        
        Returns:
            float: Factor de distancia normalizado (0.3 = muy cerca, 3.0 = muy lejos)
        """
        try:
            # Usar puntos clave estables: muñeca + base de cada dedo
            puntos_clave = [0, 5, 9, 13, 17]  # Wrist + MCP de cada dedo
            z_valores = [landmarks.landmark[i].z for i in puntos_clave]
            z_promedio = np.mean(z_valores)
            
            # Normalizar a escala útil
            # z_promedio típicamente varía entre -0.5 (muy cerca) y 0.5 (lejos)
            # Convertimos a factor multiplicador: 1.0 = distancia normal
            distancia_normalizada = 1.0 - (z_promedio * 1.5)
            
            # Limitar a rango razonable
            distancia_normalizada = max(0.3, min(3.0, distancia_normalizada))
            
            logger.debug(f"Distancia 3D: z_avg={z_promedio:.3f}, factor={distancia_normalizada:.2f}")
            return distancia_normalizada
            
        except Exception as e:
            logger.error(f"Error calculando distancia 3D: {e}")
            return 1.0  # Valor por defecto (distancia normal)
    
    def _calibrar_distancia_automatica(self, landmarks, frame_shape):
        """Calibra automáticamente la distancia basada en detección 3D de la mano"""
        # Usar el nuevo método 3D
        distancia_3d = self._calcular_distancia_3d_mano(landmarks)
        
        # Calcular tamaño 2D para referencia (mantener compatibilidad)
        tamaño_actual = self._calcular_tamaño_mano(landmarks, frame_shape)
        
        # Agregar al historial (máximo 10 mediciones)
        self.historial_tamaños_mano.append(tamaño_actual)
        if len(self.historial_tamaños_mano) > 10:
            self.historial_tamaños_mano.pop(0)
        
        # Calcular tamaño promedio
        tamaño_promedio = sum(self.historial_tamaños_mano) / len(self.historial_tamaños_mano)
        
        # Si es la primera vez, establecer como referencia
        if self.tamaño_mano_referencia is None:
            self.tamaño_mano_referencia = tamaño_promedio
            logger.info(f"🤚 Tamaño de mano referencia establecido: {self.tamaño_mano_referencia:.1f}")
        
        # NUEVO: Usar distancia 3D directamente como factor
        self.factor_distancia = distancia_3d
        
        # Ajustar distancia de pinza adaptativa según la distancia 3D
        # Base: configuracion.distancia_pinza (40 por defecto)
        # Multiplicar por factor 3D:
        # - Mano cerca (0.5x) = umbral más estricto (20px)
        # - Mano normal (1.0x) = umbral estándar (40px)  
        # - Mano lejos (2.0x) = umbral más permisivo (80px)
        self.distancia_pinza_adaptativa = self.configuracion.distancia_pinza * self.factor_distancia
        
        # Aplicar límites razonables
        self.distancia_pinza_adaptativa = max(15, min(100, self.distancia_pinza_adaptativa))
        
        logger.debug(f"📏 Distancia 3D: {distancia_3d:.2f}x → Umbral: {self.distancia_pinza_adaptativa:.0f}px")
    
    def _mostrar_deteccion_automatica(self, frame: np.ndarray):
        """Implementar rectángulos en esquinas para detección automática (modo backup)"""
        altura, ancho = frame.shape[:2]
        
        # Tamaño de los rectángulos de esquina
        rect_size = 50
        color = (0, 255, 255)  # Amarillo
        thickness = 3
        
        # Rectángulo superior izquierda
        cv2.rectangle(frame, (20, 20), (20 + rect_size, 20 + rect_size), color, thickness)
        cv2.putText(frame, "1", (35, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
        
        # Rectángulo superior derecha
        cv2.rectangle(frame, (ancho - 70, 20), (ancho - 20, 20 + rect_size), color, thickness)
        cv2.putText(frame, "2", (ancho - 55, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
        
        # Rectángulo inferior derecha
        cv2.rectangle(frame, (ancho - 70, altura - 70), (ancho - 20, altura - 20), color, thickness)
        cv2.putText(frame, "3", (ancho - 55, altura - 35), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
        
        # Rectángulo inferior izquierda
        cv2.rectangle(frame, (20, altura - 70), (20 + rect_size, altura - 20), color, thickness)
        cv2.putText(frame, "4", (35, altura - 35), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
        
        # Texto informativo
        cv2.putText(frame, "MODO DETECCION: Apunta a rectangulos 1-2-3-4", 
                   (ancho//2 - 200, altura - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    
    def dibujar_interfaz_principal(self, frame: np.ndarray) -> np.ndarray:
        """Dibuja la interfaz principal del sistema"""
        altura, ancho = frame.shape[:2]
        
        # Solo dibujar la información básica, sin botones falsos
        self._dibujar_informacion_sistema(frame)
        
        if self.mostrar_interfaz:
            self._dibujar_interfaz_completa(frame)
        
        return frame
    
    def _dibujar_informacion_sistema(self, frame: np.ndarray):
        """Dibuja información básica del sistema sin botones falsos"""
        altura, ancho = frame.shape[:2]
        barra_alto = 40
        
        # Fondo simple para información
        cv2.rectangle(frame, (0, 0), (ancho, barra_alto), (30, 30, 30), -1)
        cv2.rectangle(frame, (0, 0), (ancho, barra_alto), (80, 80, 80), 1)
        
        # Información básica del sistema
        info_texto = f"Detector de Gestos v3.0 - {self.modo.value.title()}"
        cv2.putText(frame, info_texto, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 
                   0.7, (255, 255, 255), 2)
        
        # Estado de calibración si aplica
        if self.modo == ModoOperacion.MESA:
            puntos_cal = len(self.puntos_camara)
            if puntos_cal >= 4:
                estado_cal = "Calibrado ✓"
                color_cal = (0, 255, 0)
            else:
                estado_cal = f"Sin calibrar ({puntos_cal}/4)"
                color_cal = (255, 100, 0)
            
            cv2.putText(frame, estado_cal, (ancho - 200, 25), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.6, color_cal, 2)
    
    def _dibujar_interfaz_completa(self, frame: np.ndarray):
        """Dibuja la interfaz completa con información detallada en panel lateral derecho"""
        altura, ancho = frame.shape[:2]
        
        # 📊 PANEL LATERAL DERECHO REORGANIZADO
        panel_ancho = 320
        panel_x = ancho - panel_ancho
        
        # Fondo del panel derecho completo
        cv2.rectangle(frame, (panel_x, 0), (ancho, altura), (25, 25, 25), -1)
        cv2.rectangle(frame, (panel_x, 0), (ancho, altura), (80, 80, 80), 2)
        
        # Título principal
        y_pos = 30
        cv2.putText(frame, "DETECTOR GESTOS v3.0", (panel_x + 10, y_pos), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # Separador
        y_pos += 10
        cv2.line(frame, (panel_x + 10, y_pos), (ancho - 10, y_pos), (100, 100, 100), 1)
        
        # INFORMACIÓN DEL SISTEMA
        y_pos += 30
        
        # INFORMACIÓN DEL SISTEMA
        y_pos += 30
        cv2.putText(frame, f"Modo: {self.modo.value.upper()}", (panel_x + 15, y_pos), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 200, 255), 1)
        
        y_pos += 25
        gesto_texto = self.ultimo_gesto.value.replace('_', ' ').title()
        cv2.putText(frame, f"Gesto: {gesto_texto}", (panel_x + 15, y_pos), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        
        y_pos += 25
        cv2.putText(frame, f"Cursor: ({self.cursor_x}, {self.cursor_y})", (panel_x + 15, y_pos), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        y_pos += 25
        cv2.putText(frame, f"Pantalla: {self.ancho_pantalla}x{self.alto_pantalla}", (panel_x + 15, y_pos), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        # INFORMACIÓN DE CALIBRACIÓN (MODO MESA)
        if self.modo == ModoOperacion.MESA:
            y_pos += 35
            cv2.putText(frame, "CALIBRACION:", (panel_x + 15, y_pos), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 0), 2)
            
            y_pos += 25
            puntos_cal = len(self.puntos_camara)
            cv2.putText(frame, f"Manual: {puntos_cal}/4 puntos", (panel_x + 15, y_pos), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 200, 0), 1)
            
            # Estado de detección automática
            y_pos += 20
            if hasattr(self, '_detectar_proyeccion_automatica') and self._detectar_proyeccion_automatica:
                if hasattr(self, 'area_proyeccion') and self.area_proyeccion:
                    estado_auto = "Auto: DETECTADO ✓"
                    color_auto = (0, 255, 0)
                else:
                    frames = getattr(self, 'marcos_sin_deteccion', 0)
                    estado_auto = f"Auto: Buscando... ({frames}/100)"
                    color_auto = (255, 200, 0)
            else:
                estado_auto = "Auto: DESACTIVADO"
                color_auto = (100, 100, 100)
            
            cv2.putText(frame, estado_auto, (panel_x + 15, y_pos), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color_auto, 1)
            
            # Información de calibración automática de distancia
            if hasattr(self, 'factor_distancia') and self.factor_distancia:
                y_pos += 20
                color_factor = (0, 255, 0) if 0.8 <= self.factor_distancia <= 1.2 else (255, 100, 0)
                cv2.putText(frame, f"Distancia: {self.factor_distancia:.2f}x", (panel_x + 15, y_pos), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, color_factor, 1)
                y_pos += 20
                cv2.putText(frame, f"Umbral: {int(self.distancia_pinza_adaptativa)}px", (panel_x + 15, y_pos), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, color_factor, 1)
            
            # Información del margen de área
            if hasattr(self, 'MARGEN_AREA'):
                y_pos += 20
                cv2.putText(frame, f"Margen: {self.MARGEN_AREA}px", (panel_x + 15, y_pos), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 200, 255), 1)
        
        # CONTROLES DE TECLADO
        y_pos += 45
        cv2.putText(frame, "CONTROLES:", (panel_x + 15, y_pos), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        controles = [
            "ESC/Q - Salir",
            "V - Mostrar/Ocultar UI", 
            "M - Modo (Pantalla/Mesa)",
            "K - Cambiar camara",
            "C - Calibracion manual",
            "A - Deteccion automatica",
            "R - Reset sistema",
            "+/- - Ajustar margen (Mesa)"
        ]
        
        y_pos += 25
        for control in controles:
            cv2.putText(frame, control, (panel_x + 15, y_pos), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
            y_pos += 18
        
        # GESTOS DISPONIBLES
        y_pos += 15
        cv2.putText(frame, "GESTOS:", (panel_x + 15, y_pos), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        gestos = [
            "🖐️ Mano abierta - Cursor",
            "👌 Pulgar+Indice - Click L",
            "🤏 Pulgar+Medio - Click R", 
            "⚡ Doble pinza - Doble click",
            "👊👊 Dos manos - Zoom"
        ]
        
        y_pos += 25
        for gesto in gestos:
            cv2.putText(frame, gesto, (panel_x + 15, y_pos), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 255, 150), 1)
            y_pos += 18
        
        # Panel lateral con controles (COMENTADO - ya está integrado arriba)
        # self._dibujar_panel_controles_simple(frame)
    
    def _dibujar_panel_controles_simple(self, frame: np.ndarray):
        """Dibuja un panel de controles simplificado"""
        altura, ancho = frame.shape[:2]
        panel_ancho = 280
        panel_x = ancho - panel_ancho
        panel_y = 50
        panel_alto = 180
        
        # Fondo del panel
        cv2.rectangle(frame, (panel_x, panel_y), (ancho, panel_y + panel_alto), (30, 30, 30), -1)
        cv2.rectangle(frame, (panel_x, panel_y), (ancho, panel_y + panel_alto), (100, 100, 100), 2)
        
        # Título
        y_pos = panel_y + 30
        cv2.putText(frame, "CONTROLES DE TECLADO:", (panel_x + 15, y_pos), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Lista de controles
        controles = [
            "ESC/Q - Salir del programa",
            "V - Mostrar/Ocultar interfaz", 
            "M - Cambiar modo (Pantalla/Mesa)",
            "K - Cambiar camara",
            "C - Calibracion manual (modo mesa)",
            "A - Deteccion automatica (modo mesa)",
            "R - Reset calibracion/zoom",
            "",
        ]
        
        y_pos += 25
        for control in controles:
            if control == "":
                y_pos += 10
                continue
            elif control.startswith("GESTOS"):
                cv2.putText(frame, control, (panel_x + 15, y_pos), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            else:
                cv2.putText(frame, control, (panel_x + 15, y_pos), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
            y_pos += 15
    
    def _dibujar_panel_controles(self, frame: np.ndarray):
        """Dibuja el panel de controles lateral"""
        altura, ancho = frame.shape[:2]
        panel_ancho = 300
        panel_x = ancho - panel_ancho
        
        # Fondo del panel
        cv2.rectangle(frame, (panel_x, 0), (ancho, altura), (0, 0, 0), -1)
        cv2.rectangle(frame, (panel_x, 0), (ancho, altura), self.configuracion.color_primario, 2)
        
        # Información del sistema
        y_pos = 30
        cv2.putText(frame, "CONTROLES", (panel_x + 10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 
                   0.7, self.configuracion.color_secundario, 2)
        
        y_pos += 40
        cv2.putText(frame, "V - Alternar interfaz", (panel_x + 10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 
                   0.5, (255, 255, 255), 1)
        
        y_pos += 25
        cv2.putText(frame, "ESC - Salir", (panel_x + 10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 
                   0.5, (255, 255, 255), 1)
        
        # Información de calibración
        if self.modo == ModoOperacion.MESA:
            y_pos += 50
            cv2.putText(frame, "CALIBRACION", (panel_x + 10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.7, self.configuracion.color_secundario, 2)
            
            y_pos += 30
            puntos_cal = len(self.puntos_camara)
            cv2.putText(frame, f"Puntos: {puntos_cal}/4", (panel_x + 10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.5, (255, 255, 255), 1)
            
            if puntos_cal < 4:
                y_pos += 25
                cv2.putText(frame, "Toca las esquinas", (panel_x + 10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 
                           0.5, self.configuracion.color_error, 1)
    
    def _dibujar_panel_gestos(self, frame: np.ndarray):
        """Dibuja el panel de información de gestos"""
        altura, ancho = frame.shape[:2]
        panel_alto = 100
        panel_y = altura - panel_alto
        
        # Fondo del panel
        cv2.rectangle(frame, (0, panel_y), (ancho - 300, altura), (0, 0, 0), -1)
        cv2.rectangle(frame, (0, panel_y), (ancho - 300, altura), self.configuracion.color_primario, 2)
        
        # Información de gestos
        y_pos = panel_y + 30
        cv2.putText(frame, "GESTOS DISPONIBLES", (10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 
                   0.7, self.configuracion.color_secundario, 2)
        
        y_pos += 30
        cv2.putText(frame, "✋ Mano abierta: Cursor | 👌 Pulgar+Indice: Click/Arrastrar | 🤏 Pulgar+Medio: Click derecho", 
                   (10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        y_pos += 25
        cv2.putText(frame, f"👊 Dos puños: Zoom | Doble click: {self.doble_click_ventana}s", 
                   (10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    
    def procesar_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, InfoGesto]:
        """
        Procesa un frame y detecta gestos
        
        Args:
            frame: Frame de la cámara
            
        Returns:
            Tuple con frame procesado e información del gesto
        """
        # Convertir de BGR a RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Detectar manos
        resultados = self.hands.process(rgb_frame)
        
        # DETECCIÓN AUTOMÁTICA DE PROYECCIÓN (solo en modo MESA)
        if hasattr(self, '_detectar_proyeccion_automatica') and self._detectar_proyeccion_automatica and self.modo == ModoOperacion.MESA:
            
            if not hasattr(self, 'area_proyeccion') or self.area_proyeccion is None:
                # Intentar detectar área de proyección cada 10 frames
                if not hasattr(self, '_frame_count_deteccion'):
                    self._frame_count_deteccion = 0
                
                self._frame_count_deteccion += 1
                if self._frame_count_deteccion % 10 == 0:  # Cada 10 frames (más frecuente)
                    logger.info(f"🔍 Intentando detectar proyección (frame {self._frame_count_deteccion})")
                    area_detectada = self._detectar_area_proyeccion(frame)
                    if area_detectada:
                        self.area_proyeccion = area_detectada
                        logger.info(f"✅ Área de proyección detectada automáticamente: {area_detectada}")
                        # Configurar matriz de transformación automática
                        self._configurar_transformacion_automatica()
                    else:
                        logger.debug(f"⚪ No se detectó proyección en frame {self._frame_count_deteccion}")
            
            # Dibujar área de proyección si está detectada
            if hasattr(self, 'area_proyeccion') and self.area_proyeccion:
                self._dibujar_area_proyeccion(frame)
        
        # Información del gesto por defecto
        info_gesto = InfoGesto(gesto=TipoGesto.NINGUNO)
        
        if resultados.multi_hand_landmarks:
            if len(resultados.multi_hand_landmarks) == 1:
                # Una mano detectada - resetear zoom
                self.zoom_activo = False
                self.distancia_puños_anterior = 0
                info_gesto = self._detectar_gestos_una_mano(
                    resultados.multi_hand_landmarks[0], frame
                )
            elif len(resultados.multi_hand_landmarks) == 2:
                # Dos manos detectadas - posible zoom
                info_gesto = self._detectar_gestos_dos_manos(
                    resultados.multi_hand_landmarks, frame
                )
            
            # Dibujar landmarks
            for hand_landmarks in resultados.multi_hand_landmarks:
                self.mp_drawing.draw_landmarks(
                    frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS
                )
        else:
            # No hay manos - resetear zoom
            self.zoom_activo = False
            self.distancia_puños_anterior = 0
        
        # Ejecutar acción según el gesto
        self._ejecutar_accion(info_gesto)
        
        # Actualizar estado
        self.ultimo_gesto = info_gesto.gesto
        self.tiempo_gesto = time.time()
        
        # Dibujar interfaz
        frame = self.dibujar_interfaz_principal(frame)
        
        # Dibujar indicadores de gesto
        self._dibujar_indicadores_gestos(frame, info_gesto)
        
        return frame, info_gesto
    
    def _detectar_gestos_una_mano(self, landmarks, frame: np.ndarray) -> InfoGesto:
        """Detecta gestos con una sola mano"""
        altura, ancho = frame.shape[:2]
        
        # 🔧 CALIBRACIÓN AUTOMÁTICA DE DISTANCIA
        self._calibrar_distancia_automatica(landmarks, (altura, ancho))
        
        # Si estamos calibrando, procesar calibración
        if self.calibrando and not self.esperando_confirmacion:
            self._procesar_calibracion(frame, landmarks)
        elif self.esperando_confirmacion:
            self._procesar_confirmacion_calibracion(frame, landmarks)
            return InfoGesto(gesto=TipoGesto.NINGUNO)
        
        # Convertir landmarks a coordenadas de píxeles
        puntos = []
        for landmark in landmarks.landmark:
            x = int(landmark.x * ancho)
            y = int(landmark.y * altura)
            puntos.append((x, y))
        
        # Obtener puntos clave
        pulgar_tip = puntos[4]
        indice_tip = puntos[8]
        medio_tip = puntos[12]
        
        # 🚫 FILTRO PRINCIPAL: En modo MESA con área detectada, ignorar manos fuera del área
        if (self.modo == ModoOperacion.MESA and 
            hasattr(self, 'area_proyeccion') and self.area_proyeccion):
            # Verificar si el índice (punto principal de control) está dentro del área
            if not self._punto_dentro_proyeccion(indice_tip[0], indice_tip[1]):
                # Mano fuera del área de proyección - ignorar completamente
                return InfoGesto(gesto=TipoGesto.NINGUNO)
        
        # Calcular distancias para gestos de pinza
        distancia_pulgar_indice = np.sqrt((pulgar_tip[0] - indice_tip[0])**2 + 
                                         (pulgar_tip[1] - indice_tip[1])**2)
        distancia_pulgar_medio = np.sqrt((pulgar_tip[0] - medio_tip[0])**2 + 
                                        (pulgar_tip[1] - medio_tip[1])**2)
        
        # Determinar gesto
        tiempo_actual = time.time()
        
        # Click izquierdo con pinza pulgar+índice (permite arrastre)
        if distancia_pulgar_indice < self.distancia_pinza_adaptativa:
            # Solo permitir click si la mano está cerca o la pinza está muy cerrada
            if getattr(self, 'factor_distancia', 1.0) > 0.7 or distancia_pulgar_indice < 20:
                posicion_click = ((pulgar_tip[0] + indice_tip[0]) // 2, (pulgar_tip[1] + indice_tip[1]) // 2)
                
                # 🚫 FILTRAR CLICKS FUERA DEL ÁREA DE PROYECCIÓN
                if (self.modo == ModoOperacion.MESA and 
                    hasattr(self, 'area_proyeccion') and self.area_proyeccion and
                    not self._punto_dentro_proyeccion(posicion_click[0], posicion_click[1])):
                    # Si está fuera del área, retornar cursor normal usando PULGAR
                    return InfoGesto(
                        gesto=TipoGesto.CURSOR,
                        posicion=pulgar_tip,
                        confianza=0.7
                    )
                
                # Click izquierdo con soporte de arrastre
                return InfoGesto(
                    gesto=TipoGesto.CLICK_IZQUIERDO,
                    posicion=posicion_click,
                    confianza=0.9
                )
            # Si no cumple la condición de distancia, solo cursor usando PULGAR
            else:
                return InfoGesto(
                    gesto=TipoGesto.CURSOR,
                    posicion=pulgar_tip,
                    confianza=0.7
                )
        
        elif distancia_pulgar_medio < self.distancia_pinza_adaptativa:
            # Click derecho
            posicion_click = ((pulgar_tip[0] + medio_tip[0]) // 2, (pulgar_tip[1] + medio_tip[1]) // 2)
            
            # 🚫 FILTRAR CLICKS DERECHOS FUERA DEL ÁREA DE PROYECCIÓN
            if (self.modo == ModoOperacion.MESA and 
                hasattr(self, 'area_proyeccion') and self.area_proyeccion and
                not self._punto_dentro_proyeccion(posicion_click[0], posicion_click[1])):
                # Si está fuera del área, retornar cursor normal usando PULGAR
                return InfoGesto(
                    gesto=TipoGesto.CURSOR,
                    posicion=pulgar_tip,
                    confianza=0.7
                )
            
            return InfoGesto(
                gesto=TipoGesto.CLICK_DERECHO,
                posicion=posicion_click,
                confianza=0.9
            )
        
        else:
            # Cursor (mano abierta) - usar el PULGAR como punto de control
            # Esto es más natural: mueves el pulgar y bajas el índice para hacer click
            posicion_suavizada = self._suavizar_movimiento(pulgar_tip[0], pulgar_tip[1])
            return InfoGesto(
                gesto=TipoGesto.CURSOR,
                posicion=posicion_suavizada,
                confianza=0.8
            )
    
    def _detectar_gestos_dos_manos(self, landmarks_list, frame: np.ndarray) -> InfoGesto:
        """Detecta gestos con dos manos (zoom)"""
        altura, ancho = frame.shape[:2]
        
        # Obtener posiciones de las muñecas de ambas manos
        mano1 = landmarks_list[0].landmark[0]  # Muñeca mano 1
        mano2 = landmarks_list[1].landmark[0]  # Muñeca mano 2
        
        pos1 = (int(mano1.x * ancho), int(mano1.y * altura))
        pos2 = (int(mano2.x * ancho), int(mano2.y * altura))
        
        # Calcular distancia entre manos
        distancia_actual = np.sqrt((pos1[0] - pos2[0])**2 + (pos1[1] - pos2[1])**2)
        
        # Si es la primera vez o el zoom no estaba activo, inicializar
        if not self.zoom_activo or self.distancia_puños_anterior == 0:
            self.zoom_activo = True
            self.distancia_puños_anterior = distancia_actual
            return InfoGesto(gesto=TipoGesto.NINGUNO)
        
        # Calcular diferencia con umbral más pequeño para mejor sensibilidad
        diferencia = distancia_actual - self.distancia_puños_anterior
        umbral_minimo = 15  # píxeles de cambio mínimo para detectar zoom
        
        resultado = InfoGesto(gesto=TipoGesto.NINGUNO)
        
        if diferencia > umbral_minimo:
            # Manos se alejan = Zoom in
            resultado = InfoGesto(
                gesto=TipoGesto.ZOOM_IN,
                posicion=((pos1[0] + pos2[0]) // 2, (pos1[1] + pos2[1]) // 2),
                confianza=0.8
            )
            logger.debug(f"Zoom IN detectado: distancia {self.distancia_puños_anterior:.1f} → {distancia_actual:.1f} (diff: +{diferencia:.1f})")
        elif diferencia < -umbral_minimo:
            # Manos se acercan = Zoom out
            resultado = InfoGesto(
                gesto=TipoGesto.ZOOM_OUT,
                posicion=((pos1[0] + pos2[0]) // 2, (pos1[1] + pos2[1]) // 2),
                confianza=0.8
            )
            logger.debug(f"Zoom OUT detectado: distancia {self.distancia_puños_anterior:.1f} → {distancia_actual:.1f} (diff: {diferencia:.1f})")
        
        # Actualizar distancia anterior solo si hubo un cambio significativo
        if abs(diferencia) > umbral_minimo:
            self.distancia_puños_anterior = distancia_actual
        
        return resultado
    
    def _suavizar_movimiento(self, x: int, y: int) -> Tuple[int, int]:
        """Aplica suavizado al movimiento del cursor"""
        self.historial_x.append(x)
        self.historial_y.append(y)
        
        if len(self.historial_x) > self.suavizado:
            self.historial_x.pop(0)
        if len(self.historial_y) > self.suavizado:
            self.historial_y.pop(0)
        
        x_suavizado = int(np.mean(self.historial_x))
        y_suavizado = int(np.mean(self.historial_y))
        
        # Filtro de estabilización para "Modo Precisión"
        # Si el movimiento es muy pequeño, mantener la posición anterior para evitar "jitter"
        if hasattr(self, 'modo_precision') and self.modo_precision:
            distancia = np.sqrt((x_suavizado - self.posicion_estable[0])**2 + (y_suavizado - self.posicion_estable[1])**2)
            if distancia < self.umbral_estabilidad:
                return self.posicion_estable
            else:
                self.posicion_estable = (x_suavizado, y_suavizado)
                return (x_suavizado, y_suavizado)
        
        return (x_suavizado, y_suavizado)
    
    def _ejecutar_accion(self, info_gesto: InfoGesto):
        """Ejecuta la acción correspondiente al gesto detectado"""
        if info_gesto.gesto == TipoGesto.CURSOR and info_gesto.posicion:
            # Si el botón estaba presionado y ahora es cursor (mano abierta), soltar
            if self.boton_presionado:
                try:
                    pyautogui.mouseUp()
                    self.boton_presionado = False
                    self.arrastrando = False
                    logger.info("Click soltado (arrastre terminado)")
                except pyautogui.FailSafeException:
                    logger.warning("FailSafe activado - mouseUp cancelado")
            self._mover_cursor(info_gesto.posicion)
        
        elif info_gesto.gesto == TipoGesto.CLICK_IZQUIERDO:
            # Presionar el botón si no está presionado (inicia arrastre)
            if not self.boton_presionado:
                try:
                    pyautogui.mouseDown()
                    self.boton_presionado = True
                    self.arrastrando = True
                    self.ultimo_click_tiempo = time.time()
                    logger.info("Click izquierdo presionado (arrastre iniciado)")
                except pyautogui.FailSafeException:
                    logger.warning("FailSafe activado - mouseDown cancelado")
            # Si ya está presionado, solo mover (continuar arrastre)
            elif info_gesto.posicion:
                self._mover_cursor(info_gesto.posicion)
        
        elif info_gesto.gesto == TipoGesto.DOBLE_CLICK:
            self._realizar_doble_click()
        
        elif info_gesto.gesto == TipoGesto.CLICK_DERECHO:
            self._realizar_click_derecho()
        
        elif info_gesto.gesto == TipoGesto.ZOOM_IN:
            self._realizar_zoom(self.configuracion.factor_zoom_in)
        
        elif info_gesto.gesto == TipoGesto.ZOOM_OUT:
            self._realizar_zoom(self.configuracion.factor_zoom_out)
    
    def _mover_cursor(self, posicion: Tuple[int, int]):
        """Mueve el cursor a la posición especificada"""
        # NUEVA LÓGICA: Verificar si está en modo mesa con detección automática
        if (self.modo == ModoOperacion.MESA and 
            hasattr(self, 'area_proyeccion') and self.area_proyeccion):
            
            # Verificar si el punto está dentro del área de proyección
            if not self._punto_dentro_proyeccion(posicion[0], posicion[1]):
                # Si está fuera del área, no procesar el gesto
                return
            
            # Mapear coordenadas del área de proyección a pantalla
            posicion = self._mapear_coordenadas_proyeccion(posicion[0], posicion[1])
            
        elif self.modo == ModoOperacion.MESA and len(self.puntos_camara) >= 4:
            # Usar calibración manual existente
            posicion = self._transformar_coordenadas(posicion)
        else:
            # Mapear directamente a la pantalla (modo pantalla)
            # Obtener dimensiones reales del frame
            ancho_frame = 640  # Se puede obtener dinámicamente
            alto_frame = 480
            
            x_pantalla = int(posicion[0] * self.ancho_pantalla / ancho_frame)
            y_pantalla = int(posicion[1] * self.alto_pantalla / alto_frame)
            posicion = (x_pantalla, y_pantalla)
        
        try:
            pyautogui.moveTo(posicion[0], posicion[1], duration=0.01)
            self.cursor_x, self.cursor_y = posicion
        except pyautogui.FailSafeException:
            logger.warning("FailSafe activado - movimiento cancelado")
    
    def _realizar_click_izquierdo(self):
        """Realiza un click izquierdo"""
        try:
            pyautogui.click()
            self.ultimo_click_tiempo = time.time()
            self.arrastrando = True
            logger.info("Click izquierdo ejecutado")
        except pyautogui.FailSafeException:
            logger.warning("FailSafe activado - click cancelado")
    
    def _realizar_doble_click(self):
        """Realiza un doble click"""
        try:
            pyautogui.doubleClick()
            logger.info("Doble click ejecutado")
        except pyautogui.FailSafeException:
            logger.warning("FailSafe activado - doble click cancelado")
    
    def _realizar_click_derecho(self):
        """Realiza un click derecho"""
        try:
            pyautogui.rightClick()
            logger.info("Click derecho ejecutado")
        except pyautogui.FailSafeException:
            logger.warning("FailSafe activado - click derecho cancelado")
    
    def _realizar_zoom(self, factor: float):
        """Realiza zoom in/out"""
        if time.time() - self.cooldown_zoom > 0.1:  # Cooldown de 100ms
            try:
                if factor > 1.0:
                    pyautogui.scroll(3)  # Zoom in
                    logger.info("Zoom in ejecutado")
                else:
                    pyautogui.scroll(-3)  # Zoom out
                    logger.info("Zoom out ejecutado")
                self.cooldown_zoom = time.time()
            except pyautogui.FailSafeException:
                logger.warning("FailSafe activado - zoom cancelado")
    
    def _transformar_coordenadas(self, punto: Tuple[int, int]) -> Tuple[int, int]:
        """Transforma coordenadas de la cámara al espacio de proyección"""
        punto_h = np.array([punto[0], punto[1], 1.0])
        punto_transformado = np.dot(self.matriz_transformacion, punto_h)
        
        if punto_transformado[2] != 0:
            punto_transformado = punto_transformado / punto_transformado[2]
        
        return (int(punto_transformado[0]), int(punto_transformado[1]))
    
    def _dibujar_indicadores_gestos(self, frame: np.ndarray, info_gesto: InfoGesto):
        """Dibuja indicadores visuales de los gestos detectados"""
        if not info_gesto.posicion:
            return
        
        x, y = info_gesto.posicion
        
        # Color y texto según el tipo de gesto
        if info_gesto.gesto == TipoGesto.CURSOR:
            if info_gesto.confianza > 0.9:  # Índice extendido
                color = (0, 255, 255)  # Amarillo
                texto = "PRECISION"
                radio = 15
            else:  # Mano abierta
                color = self.configuracion.color_primario
                texto = "CURSOR"
                radio = 20
        elif info_gesto.gesto == TipoGesto.CLICK_IZQUIERDO:
            color = (255, 0, 0)  # Rojo para click izquierdo
            texto = "CLICK"
            radio = 25
        elif info_gesto.gesto == TipoGesto.DOBLE_CLICK:
            color = (255, 100, 0)
            texto = "DOBLE CLICK"
            radio = 30
        elif info_gesto.gesto == TipoGesto.CLICK_DERECHO:
            color = (0, 0, 255)
            texto = "CLICK DER"
            radio = 25
        elif info_gesto.gesto in [TipoGesto.ZOOM_IN, TipoGesto.ZOOM_OUT]:
            color = (255, 255, 0)
            texto = "ZOOM"
            radio = 35
        else:
            return
        
        # Dibujar círculo en la posición
        cv2.circle(frame, (x, y), radio, color, 3)
        cv2.circle(frame, (x, y), 5, color, -1)
        
        # Dibujar texto del gesto
        cv2.putText(frame, texto, (x - 40, y - radio - 10), cv2.FONT_HERSHEY_SIMPLEX, 
                   0.7, color, 2)
        
        # Añadir indicador de confianza
        if info_gesto.confianza > 0:
            confianza_texto = f"{int(info_gesto.confianza * 100)}%"
            cv2.putText(frame, confianza_texto, (x - 20, y + radio + 25), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.5, color, 1)
    
    def manejar_teclas(self, tecla: int) -> bool:
        """
        Maneja las teclas presionadas
        
        Args:
            tecla: Código de la tecla presionada
            
        Returns:
            True si debe continuar, False si debe salir
        """
        if tecla == 27:  # ESC
            return False
        elif tecla == ord('v') or tecla == ord('V'):  # Ver/ocultar interfaz
            self.alternar_interfaz()
        elif tecla == ord('m') or tecla == ord('M'):
            self._cambiar_modo()
        elif tecla == ord('q') or tecla == ord('Q'):
            return False
        elif tecla == ord('k') or tecla == ord('K'):  # Cambiar cámara
            self._cambiar_camara()
        elif tecla == ord('c') or tecla == ord('C'):  # Calibración
            self._iniciar_calibracion()
        elif tecla == ord('a') or tecla == ord('A'):  # Detección automática
            if self.modo == ModoOperacion.MESA:
                self._activar_deteccion_automatica()
            else:
                logger.info("⚠️  Detección automática solo disponible en modo MESA")
        elif tecla == ord('u') or tecla == ord('U'):  # Deshacer último punto
            self.deshacer_ultimo_punto()
        elif tecla == ord('r') or tecla == ord('R'):
            # Reset zoom y calibración
            self.zoom_base = 1.0
            if self.modo == ModoOperacion.MESA:
                self.puntos_camara = []
                self.puntos_proyeccion = []
                self.matriz_transformacion = np.eye(3)
                logger.info("Calibración reseteada")
            logger.info("Sistema reseteado")
        elif tecla == ord('+') or tecla == ord('='):  # Aumentar margen
            if self.modo == ModoOperacion.MESA:
                self.MARGEN_AREA = min(200, self.MARGEN_AREA + 10)
                logger.info(f"📏 Margen aumentado a {self.MARGEN_AREA}px")
        elif tecla == ord('-') or tecla == ord('_'):  # Disminuir margen
            if self.modo == ModoOperacion.MESA:
                self.MARGEN_AREA = max(0, self.MARGEN_AREA - 10)
                logger.info(f"📏 Margen reducido a {self.MARGEN_AREA}px")
        
        return True
    
    def finalizar(self):
        """Limpia recursos y finaliza el detector"""
        self.hands.close()
        logger.info("Detector de gestos finalizado")
    
    def _iniciar_confirmacion_calibracion(self):
        """Inicia el proceso de confirmación de la calibración"""
        self.esperando_confirmacion = True
        self.mostrar_preview_pantalla = True
        self.confirmacion_opcion = 0  # 0: Confirmar, 1: Recalibrar, 2: Cancelar
        logger.info("=== CALIBRACIÓN COMPLETADA ===")
        logger.info("Verifica que el rectángulo verde representa correctamente tu pantalla de proyección")
        logger.info("Usa los gestos para elegir:")
        logger.info("- Confirmar (guardar calibración)")
        logger.info("- Recalibrar (empezar de nuevo)")
        logger.info("- Cancelar (salir de calibración)")
    
    def _procesar_confirmacion_calibracion(self, frame: np.ndarray, landmarks):
        """Procesa la confirmación de calibración"""
        if not self.esperando_confirmacion:
            return
        
        altura, ancho = frame.shape[:2]
        
        # Dibujar preview del área calibrada
        if self.mostrar_preview_pantalla:
            self._dibujar_preview_pantalla_calibrada(frame)
        
        # Dibujar interfaz de confirmación
        self._dibujar_interfaz_confirmacion(frame)
        
        # Detectar gestos para navegación
        puntos = []
        for landmark in landmarks.landmark:
            x = int(landmark.x * ancho)
            y = int(landmark.y * altura)
            puntos.append((x, y))
        
        # Detectar gesto de índice extendido para selección
        if self._es_gesto_indice_extendido(puntos):
            indice_tip = landmarks.landmark[8]
            x_dedo = int(indice_tip.x * ancho)
            y_dedo = int(indice_tip.y * altura)
            
            # Verificar en qué botón está el dedo
            nueva_opcion = self._detectar_boton_confirmacion(x_dedo, y_dedo, frame)
            if nueva_opcion != -1:
                self.confirmacion_opcion = nueva_opcion
        
        # Detectar gesto de selección (puño cerrado) para confirmar opción
        if self._es_gesto_seleccion(puntos):
            if not hasattr(self, 'tiempo_seleccion_confirmacion'):
                self.tiempo_seleccion_confirmacion = time.time()
            
            tiempo_transcurrido = time.time() - self.tiempo_seleccion_confirmacion
            if tiempo_transcurrido >= 1.5:  # 1.5 segundos para confirmar
                self._ejecutar_opcion_confirmacion()
                delattr(self, 'tiempo_seleccion_confirmacion')
        else:
            if hasattr(self, 'tiempo_seleccion_confirmacion'):
                delattr(self, 'tiempo_seleccion_confirmacion')
    
    def _dibujar_preview_pantalla_calibrada(self, frame: np.ndarray):
        """Dibuja el preview del área calibrada como un rectángulo"""
        if len(self.puntos_camara) >= 4:
            # Dibujar rectángulo del área calibrada
            pts = np.array(self.puntos_camara, np.int32)
            pts = pts.reshape((-1, 1, 2))
            
            # Dibujar área rellena semi-transparente
            overlay = frame.copy()
            cv2.fillPoly(overlay, [pts], (0, 255, 0))
            cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)
            
            # Dibujar borde del rectángulo
            cv2.polylines(frame, [pts], True, (0, 255, 0), 3)
            
            # Dibujar puntos numerados
            for i, punto in enumerate(self.puntos_camara):
                cv2.circle(frame, punto, 12, (0, 255, 0), -1)
                cv2.circle(frame, punto, 15, (255, 255, 255), 2)
                cv2.putText(frame, f"{i+1}", (punto[0]-5, punto[1]+5), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    
    def _dibujar_interfaz_confirmacion(self, frame: np.ndarray):
        """Dibuja la interfaz de confirmación de calibración"""
        altura, ancho = frame.shape[:2]
        
        # Fondo para la interfaz
        cv2.rectangle(frame, (10, altura-150), (ancho-10, altura-10), (50, 50, 50), -1)
        cv2.rectangle(frame, (10, altura-150), (ancho-10, altura-10), (255, 255, 255), 2)
        
        # Título
        cv2.putText(frame, "¿El area verde representa tu pantalla correctamente?", 
                   (20, altura-120), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # Opciones con indicador de selección
        opciones = ["CONFIRMAR", "RECALIBRAR", "CANCELAR"]
        colores = [(0, 255, 0), (255, 255, 0), (0, 0, 255)]
        
        y_botones = altura - 80
        espacio_boton = (ancho - 40) // 3
        
        for i, (opcion, color) in enumerate(zip(opciones, colores)):
            x_boton = 20 + i * espacio_boton
            
            # Fondo del botón
            color_fondo = color if self.confirmacion_opcion == i else (100, 100, 100)
            cv2.rectangle(frame, (x_boton, y_botones-25), (x_boton + espacio_boton - 10, y_botones + 15), 
                         color_fondo, -1)
            cv2.rectangle(frame, (x_boton, y_botones-25), (x_boton + espacio_boton - 10, y_botones + 15), 
                         (255, 255, 255), 2)
            
            # Texto del botón
            color_texto = (0, 0, 0) if self.confirmacion_opcion == i else (255, 255, 255)
            cv2.putText(frame, opcion, (x_boton + 10, y_botones), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, color_texto, 2)
        
        # Instrucciones
        cv2.putText(frame, "Apunta con el dedo indice y cierra el puño para seleccionar", 
                   (20, altura-40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    
    def _detectar_boton_confirmacion(self, x: int, y: int, frame: np.ndarray) -> int:
        """Detecta en qué botón de confirmación está el dedo"""
        altura, ancho = frame.shape[:2]
        y_botones = altura - 80
        espacio_boton = (ancho - 40) // 3
        
        # Verificar si está en el área de botones
        if y_botones - 25 <= y <= y_botones + 15:
            for i in range(3):
                x_boton = 20 + i * espacio_boton
                if x_boton <= x <= x_boton + espacio_boton - 10:
                    return i
        return -1
    
    def _ejecutar_opcion_confirmacion(self):
        """Ejecuta la opción seleccionada en la confirmación"""
        if self.confirmacion_opcion == 0:  # Confirmar
            self._confirmar_calibracion_final()
        elif self.confirmacion_opcion == 1:  # Recalibrar
            self._reiniciar_calibracion()
        elif self.confirmacion_opcion == 2:  # Cancelar
            self._cancelar_calibracion()
    
    def _confirmar_calibracion_final(self):
        """Confirma y finaliza la calibración"""
        try:
            # Crear matriz de transformación
            self.matriz_transformacion = cv2.getPerspectiveTransform(
                np.float32(self.puntos_camara), 
                np.float32(self.puntos_proyeccion)
            )
            
            # Guardar calibración
            self._guardar_calibracion()
            
            # Resetear estado
            self.calibrando = False
            self.esperando_confirmacion = False
            self.mostrar_preview_pantalla = False
            
            logger.info("¡Calibración confirmada y guardada exitosamente!")
            logger.info("El sistema está listo para detectar gestos")
            
        except Exception as e:
            logger.error(f"Error al confirmar calibración: {e}")
            self._cancelar_calibracion()
    
    def _reiniciar_calibracion(self):
        """Reinicia el proceso de calibración"""
        self.puntos_camara.clear()
        self.puntos_proyeccion.clear()
        self.esquina_actual = 0
        self.punto_calibracion_activo = False
        self.esperando_confirmacion = False
        self.mostrar_preview_pantalla = False
        logger.info("Reiniciando calibración...")
        logger.info(f"Apunta al {self.nombres_esquinas[0]} y mantén el dedo índice extendido")
    
    def _cancelar_calibracion(self):
        """Cancela el proceso de calibración"""
        self.calibrando = False
        self.esperando_confirmacion = False
        self.mostrar_preview_pantalla = False
        self.puntos_camara.clear()
        self.puntos_proyeccion.clear()
        self.esquina_actual = 0
        self.punto_calibracion_activo = False
        logger.info("Calibración cancelada")


# ================================
# SISTEMA PRINCIPAL
# ================================

class SistemaControlGestos:
    """Sistema principal que coordina la detección y control"""
    
    def __init__(self, modo: str = "pantalla"):
        self.detector = DetectorGestos(modo)
        self.cap = None
        self.ejecutandose = False
        self.dispositivo_camara_actual = 0
        self.dispositivos_disponibles = self._detectar_camaras()
    
    def _detectar_camaras(self) -> List[int]:
        """Detecta las cámaras disponibles en el sistema - Modo simplificado para macOS"""
        # En macOS, simplemente probar cámaras comunes sin verificación profunda
        # para evitar problemas de permisos
        dispositivos = [0, 1]  # Cámara integrada y posibles externas
        logger.info(f"Usando configuración simplificada de cámaras: {dispositivos}")
        return dispositivos
    
    def cambiar_camara(self):
        """Cambia a la siguiente cámara disponible"""
        if len(self.dispositivos_disponibles) > 1:
            indice_actual = self.dispositivos_disponibles.index(self.dispositivo_camara_actual)
            siguiente_indice = (indice_actual + 1) % len(self.dispositivos_disponibles)
            nuevo_dispositivo = self.dispositivos_disponibles[siguiente_indice]
            
            # Liberar cámara actual
            if self.cap:
                self.cap.release()
            
            # Inicializar nueva cámara
            if self.inicializar_camara(nuevo_dispositivo):
                self.dispositivo_camara_actual = nuevo_dispositivo
                logger.info(f"Cambiado a cámara {nuevo_dispositivo}")
            else:
                # Si falla, volver a la anterior
                self.inicializar_camara(self.dispositivo_camara_actual)
                logger.error(f"Error cambiando a cámara {nuevo_dispositivo}")
        else:
            logger.info("Solo hay una cámara disponible")
    
    def inicializar_camara(self, dispositivo: int = 0) -> bool:
        """Inicializa la cámara - Versión simplificada para macOS"""
        try:
            logger.info(f"Intentando abrir cámara {dispositivo}")
            self.cap = cv2.VideoCapture(dispositivo)
            
            if not self.cap.isOpened():
                logger.warning(f"No se pudo abrir cámara {dispositivo}, probando alternativas...")
                
                # Probar dispositivos alternativos
                for alt_dispositivo in [1, 0, 2]:
                    if alt_dispositivo != dispositivo:
                        logger.info(f"Probando cámara {alt_dispositivo}")
                        self.cap = cv2.VideoCapture(alt_dispositivo)
                        if self.cap.isOpened():
                            self.dispositivo_camara_actual = alt_dispositivo
                            logger.info(f"✅ Cámara {alt_dispositivo} abierta exitosamente")
                            break
                        self.cap.release()
                
                if not self.cap.isOpened():
                    logger.error("❌ No se pudo abrir ninguna cámara")
                    return False
            else:
                self.dispositivo_camara_actual = dispositivo
                logger.info(f"✅ Cámara {dispositivo} abierta exitosamente")
            
            # Configurar propiedades básicas de la cámara
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.cap.set(cv2.CAP_PROP_FPS, 30)
            
            return True
            
        except Exception as e:
            logger.error(f"Error inicializando cámara: {e}")
            return False
            return False
    
    def ejecutar(self):
        """Ejecuta el bucle principal del sistema"""
        if not self.inicializar_camara(self.dispositivo_camara_actual):
            logger.error("No se pudo inicializar la cámara")
            return False
        
        logger.info("Sistema de control por gestos iniciado")
        logger.info("CONTROLES:")
        logger.info("  ESC/Q - Salir")
        logger.info("  V - Ver/ocultar interfaz")
        logger.info("  M - Cambiar modo (Pantalla/Mesa)")
        logger.info("  K - Cambiar cámara")
        logger.info("  C - Calibración (modo mesa)")
        logger.info("  U - Deshacer último punto (durante calibración)")
        logger.info("  R - Reset")
        
        self.ejecutandose = True
        
        try:
            while self.ejecutandose:
                # Verificar si se solicita salir por gesto
                if self.detector.salir_solicitado:
                    logger.info("Salida solicitada por gesto")
                    break
                
                # Verificar si se solicita cambio de cámara
                if self.detector.cambiar_camara_solicitado:
                    self.cambiar_camara()
                    self.detector.cambiar_camara_solicitado = False
                
                ret, frame = self.cap.read()
                if not ret:
                    logger.error("Error capturando frame de la cámara")
                    break
                
                # Voltear horizontalmente para mejor experiencia
                frame = cv2.flip(frame, 1)
                
                # Procesar frame
                frame_procesado, info_gesto = self.detector.procesar_frame(frame)
                
                # Mostrar información de cámara actual
                altura, ancho = frame_procesado.shape[:2]
                info_camara = f"Camara {self.dispositivo_camara_actual} | {len(self.dispositivos_disponibles)} disponibles"
                cv2.putText(frame_procesado, info_camara, (ancho - 300, altura - 20), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                
                # Mostrar resultado
                cv2.imshow('Detector de Gestos v3.0', frame_procesado)
                
                # Manejar teclas
                tecla = cv2.waitKey(1) & 0xFF
                if not self.detector.manejar_teclas(tecla):
                    break
                    
        except KeyboardInterrupt:
            logger.info("Sistema interrumpido por el usuario")
        except Exception as e:
            logger.error(f"Error en el bucle principal: {e}")
        finally:
            self.finalizar()
        
        return True
    
    def finalizar(self):
        """Finaliza el sistema y libera recursos"""
        self.ejecutandose = False
        
        if self.cap:
            self.cap.release()
        
        cv2.destroyAllWindows()
        self.detector.finalizar()
        
        logger.info("Sistema finalizado correctamente")


def main():
    """Función principal"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Sistema de Control por Gestos v3.0')
    parser.add_argument('--modo', choices=['pantalla', 'mesa'], default='pantalla',
                       help='Modo de operación: pantalla (control directo) o mesa (proyección)')
    parser.add_argument('--camara', type=int, default=0,
                       help='Índice del dispositivo de cámara (default: 0)')
    parser.add_argument('--debug', action='store_true',
                       help='Activar modo debug con logging detallado')
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    print("=" * 60)
    print("    SISTEMA DE CONTROL POR GESTOS v3.0")
    print("=" * 60)
    print(f"Modo: {args.modo}")
    print(f"Cámara: {args.camara}")
    print("Iniciando...")
    print()
    
    try:
        sistema = SistemaControlGestos(modo=args.modo)
        exito = sistema.ejecutar()
        
        if exito:
            print("\n¡Sistema ejecutado exitosamente!")
        else:
            print("\nError ejecutando el sistema")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Error crítico: {e}")
        print(f"\nError crítico: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
