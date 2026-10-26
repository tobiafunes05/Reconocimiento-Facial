"""
Script de reconocimiento facial.

Carga las fotos de los socios, codifica cada rostro en un vector de 128 valores
y compara los rostros que aparecen frente a la cámara contra esa base.

Para no recodificar las fotos en cada arranque (es lo más lento del sistema),
las codificaciones se guardan en un archivo de caché.
"""
import os
import pickle

import cv2
import numpy as np

try:
    import face_recognition as fr
    TIENE_FACE_RECOGNITION = True
except ImportError:
    fr = None
    TIENE_FACE_RECOGNITION = False

import config

EXTENSIONES = (".jpg", ".jpeg", ".png", ".bmp")


def _listar_fotos():
    """Devuelve [(nombre_socio, ruta_foto)] a partir de la carpeta de socios."""
    if not os.path.isdir(config.CARPETA_SOCIOS):
        return []
    fotos = []
    for archivo in sorted(os.listdir(config.CARPETA_SOCIOS)):
        if archivo.lower().endswith(EXTENSIONES):
            nombre = os.path.splitext(archivo)[0]
            fotos.append((nombre, os.path.join(config.CARPETA_SOCIOS, archivo)))
    return fotos


_cascade = None


def _obtener_cascade():
    global _cascade
    if _cascade is None:
        ruta = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        _cascade = cv2.CascadeClassifier(ruta)
    return _cascade


def _extraer_vector_opencv(recorte_cara):
    """Extrae un vector normalizado de 128 dimensiones de un recorte facial con OpenCV."""
    if recorte_cara is None or recorte_cara.size == 0:
        return None
    gris = cv2.cvtColor(recorte_cara, cv2.COLOR_BGR2GRAY) if len(recorte_cara.shape) == 3 else recorte_cara
    normalizado = cv2.resize(gris, (64, 64))
    celdas = []
    for i in range(4):
        for j in range(4):
            celda = normalizado[i * 16:(i + 1) * 16, j * 16:(j + 1) * 16]
            hist = cv2.calcHist([celda], [0], None, [8], [0, 256]).flatten()
            celdas.append(hist)
    vector = np.concatenate(celdas).astype(np.float32)
    norma = np.linalg.norm(vector)
    if norma > 0:
        vector = vector / norma
    return vector


def codificar_foto(ruta):
    """Devuelve la codificación del primer rostro de una imagen, o None si no hay ninguno."""
    if TIENE_FACE_RECOGNITION:
        imagen = fr.load_image_file(ruta)
        codificaciones = fr.face_encodings(imagen)
        return codificaciones[0] if codificaciones else None

    # Fallback OpenCV
    img = cv2.imread(ruta)
    if img is None:
        return None
    gris = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    caras = _obtener_cascade().detectMultiScale(gris, scaleFactor=1.1, minNeighbors=4, minSize=(30, 30))
    if len(caras) == 0:
        h, w = img.shape[:2]
        recorte = img[h // 6:5 * h // 6, w // 6:5 * w // 6]
        return _extraer_vector_opencv(recorte)
    x, y, w, h = caras[0]
    recorte = img[y:y + h, x:x + w]
    return _extraer_vector_opencv(recorte)


def cargar_base(forzar=False):
    """
    Devuelve (nombres, codificaciones) de todos los socios.
    Usa el caché salvo que las fotos hayan cambiado o se pida forzar.
    """
    fotos = _listar_fotos()
    firma = {nombre: os.path.getmtime(ruta) for nombre, ruta in fotos}

    if not forzar and os.path.exists(config.RUTA_CACHE):
        try:
            with open(config.RUTA_CACHE, "rb") as f:
                cache = pickle.load(f)
            if cache.get("firma") == firma:
                return cache["nombres"], cache["codificaciones"]
        except Exception:
            pass   # caché dañado: se vuelve a generar

    nombres, codificaciones, sin_rostro = [], [], []
    for nombre, ruta in fotos:
        codificacion = codificar_foto(ruta)
        if codificacion is None:
            sin_rostro.append(nombre)
            continue
        nombres.append(nombre)
        codificaciones.append(codificacion)

    if sin_rostro:
        print(f"[!] No se detecto ningun rostro en: {', '.join(sin_rostro)}")

    os.makedirs(os.path.dirname(config.RUTA_CACHE), exist_ok=True)
    with open(config.RUTA_CACHE, "wb") as f:
        pickle.dump({"firma": firma, "nombres": nombres, "codificaciones": codificaciones}, f)
    return nombres, codificaciones


def identificar(codificacion_cara, nombres, codificaciones, tolerancia=None):
    """
    Compara un rostro contra la base de socios.
    Devuelve (nombre, distancia). El nombre es None si no coincide con nadie.
    """
    tolerancia = config.TOLERANCIA if tolerancia is None else tolerancia
    if not codificaciones or codificacion_cara is None:
        return None, 1.0

    if TIENE_FACE_RECOGNITION:
        distancias = fr.face_distance(codificaciones, codificacion_cara)
        indice = int(np.argmin(distancias))         # el socio más parecido
        distancia = float(distancias[indice])
        if distancia > tolerancia:
            return None, distancia
        return nombres[indice], distancia

    # Fallback distancia para vector de OpenCV
    arr_cods = np.array(codificaciones)
    distancias = 0.5 * np.linalg.norm(arr_cods - codificacion_cara, axis=1)
    indice = int(np.argmin(distancias))
    distancia = float(distancias[indice])
    if distancia > 0.65:
        return None, distancia
    return nombres[indice], distancia


def buscar_rostros(fotograma):
    """
    Detecta y codifica los rostros de un fotograma de la cámara.
    Devuelve [(ubicacion_en_tamaño_original, codificacion)].
    El fotograma se achica antes de procesarlo para que el video vaya fluido.
    """
    escala = config.ESCALA_PROCESO
    chico = cv2.resize(fotograma, (0, 0), fx=escala, fy=escala)

    if TIENE_FACE_RECOGNITION:
        rgb = cv2.cvtColor(chico, cv2.COLOR_BGR2RGB)
        ubicaciones = fr.face_locations(rgb, model=config.MODELO_DETECCION)
        codificaciones = fr.face_encodings(rgb, ubicaciones)
        resultado = []
        for (arriba, derecha, abajo, izquierda), codificacion in zip(ubicaciones, codificaciones):
            ubicacion = (int(arriba / escala), int(derecha / escala),
                         int(abajo / escala), int(izquierda / escala))
            resultado.append((ubicacion, codificacion))
        return resultado

    # Fallback con Haar Cascades de OpenCV
    gris = cv2.cvtColor(chico, cv2.COLOR_BGR2GRAY)
    caras = _obtener_cascade().detectMultiScale(gris, scaleFactor=1.15, minNeighbors=4, minSize=(25, 25))
    resultado = []
    for (x, y, w, h) in caras:
        recorte = chico[y:y + h, x:x + w]
        cod = _extraer_vector_opencv(recorte)
        ubicacion = (int(y / escala), int((x + w) / escala),
                     int((y + h) / escala), int(x / escala))
        resultado.append((ubicacion, cod))
    return resultado


def dibujar_rostro(fotograma, ubicacion, etiqueta, color, subtitulo=None):
    """Dibuja el recuadro del rostro con el nombre y el estado del acceso."""
    arriba, derecha, abajo, izquierda = ubicacion
    cv2.rectangle(fotograma, (izquierda, arriba), (derecha, abajo), color, 2)
    cv2.rectangle(fotograma, (izquierda, abajo - 38), (derecha, abajo), color, cv2.FILLED)
    cv2.putText(fotograma, etiqueta, (izquierda + 6, abajo - 12),
                cv2.FONT_HERSHEY_DUPLEX, 0.6, (255, 255, 255), 1)
    if subtitulo:
        cv2.rectangle(fotograma, (izquierda, abajo), (derecha, abajo + 26), (35, 35, 35), cv2.FILLED)
        cv2.putText(fotograma, subtitulo[:42], (izquierda + 6, abajo + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
