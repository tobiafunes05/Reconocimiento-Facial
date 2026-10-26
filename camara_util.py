"""
Utilidad centralizada para manejo de cámaras con OpenCV.
Optimizado para Windows (DirectShow) con detección automática de índice y prevención de bloqueos.
"""
import os
import time
import cv2
import config


def abrir_camara(indice=None, fallback_indices=True):
    """
    Abre la cámara especificada utilizando DirectShow en Windows (más rápido y estable).
    Si el índice falla y fallback_indices es True, intenta detectar automáticamente
    otra cámara disponible (índices 0, 1, 2).
    """
    idx_solicitado = config.INDICE_CAMARA if indice is None else indice
    indices_a_probar = [idx_solicitado]
    if fallback_indices:
        for i in [0, 1, 2]:
            if i not in indices_a_probar:
                indices_a_probar.append(i)

    for idx in indices_a_probar:
        cap = None
        # En Windows probar primero cv2.CAP_DSHOW para apertura instantánea
        if os.name == "nt":
            try:
                cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                if cap.isOpened():
                    # Verificar que realmente lea fotogramas
                    exito, _ = cap.read()
                    if exito:
                        return cap
                    cap.release()
            except Exception:
                if cap:
                    cap.release()

        # Fallback con backend por defecto
        try:
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                exito, _ = cap.read()
                if exito:
                    return cap
                cap.release()
        except Exception:
            if cap:
                cap.release()

    return None


def capturar_fotograma_directo(indice=None):
    """
    Abre la cámara brevemente, descarta los primeros fotogramas para estabilizar
    la exposición/balance de blancos, captura una foto limpia y libera la cámara.
    Devuelve (exito, fotograma).
    """
    cap = abrir_camara(indice=indice)
    if not cap:
        return False, None

    try:
        # Descartar primeros fotogramas para estabilizar sensor
        for _ in range(4):
            cap.read()
            time.sleep(0.05)

        exito, fotograma = cap.read()
        if exito and fotograma is not None:
            return True, fotograma
        return False, None
    finally:
        cap.release()


def listar_camaras_disponibles(max_camaras=3):
    """Devuelve una lista con los índices de cámaras disponibles en el sistema."""
    disponibles = []
    for idx in range(max_camaras):
        cap = None
        if os.name == "nt":
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        else:
            cap = cv2.VideoCapture(idx)
        if cap and cap.isOpened():
            exito, _ = cap.read()
            if exito:
                disponibles.append(idx)
            cap.release()
    return disponibles
