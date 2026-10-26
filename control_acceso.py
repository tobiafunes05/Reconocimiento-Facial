"""
Script de asistencias: control de acceso en tiempo real.

Abre la cámara, reconoce las caras que aparecen, consulta el motor de reglas
y registra la entrada o la salida de cada socio.

La misma cámara sirve para entrar y para salir: si el socio está afuera se
registra su entrada; si ya está adentro, se le registra la salida y se calculan
las horas consumidas.
"""
import os
import time
from datetime import datetime

import cv2

import base_datos as bd
import config
import reconocimiento as rec
import reglas

# Personas fichadas hace poco: evita registrar muchas veces seguidas
# a quien se queda parado frente a la cámara.
_ultimo_fichaje = {}


def _en_espera(nombre):
    ultimo = _ultimo_fichaje.get(nombre)
    return ultimo is not None and (time.time() - ultimo) < config.SEGUNDOS_ESPERA


def _guardar_foto_intento(fotograma, ubicacion):
    """Guarda el recorte del rostro de un acceso rechazado o desconocido."""
    os.makedirs(config.CARPETA_INTENTOS, exist_ok=True)
    arriba, derecha, abajo, izquierda = ubicacion
    margen = 40
    alto, ancho = fotograma.shape[:2]
    recorte = fotograma[max(arriba - margen, 0):min(abajo + margen, alto),
                        max(izquierda - margen, 0):min(derecha + margen, ancho)]
    ruta = os.path.join(config.CARPETA_INTENTOS,
                        f"intento_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
    if recorte.size:
        cv2.imwrite(ruta, recorte)
        return ruta
    return None


def procesar_socio(nombre, fotograma=None, ubicacion=None):
    """
    Decide y ejecuta qué corresponde para un socio reconocido.
    Devuelve (decision, etiqueta, detalle) para mostrar en pantalla.
    """
    socio = bd.obtener_socio(nombre)
    if socio is None:
        return reglas.RECHAZADO, nombre, "No figura en el sistema"

    socio = bd.reiniciar_periodo_si_cambio_mes(socio)
    abierto = bd.registro_abierto(socio["id"])

    # ---- La persona está adentro: se registra la SALIDA ----
    if abierto:
        entrada = datetime.strptime(abierto["entrada"], "%Y-%m-%d %H:%M:%S")
        horas = round((datetime.now() - entrada).total_seconds() / 3600, 2)
        dentro, excedente, importe = reglas.calcular_consumo(socio, horas)
        bd.registrar_salida(abierto["id"], horas, excedente)
        bd.sumar_horas_usadas(socio["id"], horas)

        detalle = f"Sesion de {horas:.2f} h"
        if excedente > 0:
            detalle += f" | {excedente:.2f} h excedente (${importe:,.0f})"
        return reglas.HABILITADO, f"CHAU {nombre}", detalle

    # ---- La persona está afuera: se evalúa la ENTRADA ----
    analisis = reglas.evaluar_acceso(socio, bd.cantidad_adentro(), bd.reserva_de_hoy(socio["id"]))

    if analisis["decision"] == reglas.RECHAZADO:
        foto = _guardar_foto_intento(fotograma, ubicacion) if fotograma is not None else None
        bd.registrar_intento(nombre, analisis["motivo"], foto)
        return reglas.RECHAZADO, nombre, analisis["motivo"]

    bd.registrar_entrada(socio["id"], nombre)
    detalle = " | ".join(analisis["avisos"]) if analisis["avisos"] else config.PLANES[socio["plan"]]["nombre"]
    return analisis["decision"], f"HOLA {nombre}", detalle


def _color(decision):
    return {reglas.HABILITADO: config.COLOR_HABILITADO,
            reglas.ADVERTENCIA: config.COLOR_ADVERTENCIA,
            reglas.RECHAZADO: config.COLOR_RECHAZADO}.get(decision, config.COLOR_DESCONOCIDO)


def _barra_estado(fotograma):
    """Franja superior con el nombre del espacio, el aforo y la hora."""
    ancho = fotograma.shape[1]
    adentro = bd.cantidad_adentro()
    cv2.rectangle(fotograma, (0, 0), (ancho, 40), (30, 30, 30), cv2.FILLED)
    cv2.putText(fotograma, config.NOMBRE_ESPACIO, (12, 27),
                cv2.FONT_HERSHEY_DUPLEX, 0.6, (255, 255, 255), 1)
    texto = f"Adentro: {adentro}/{config.AFORO_MAXIMO}   {datetime.now().strftime('%d/%m %H:%M:%S')}"
    color = config.COLOR_RECHAZADO if adentro >= config.AFORO_MAXIMO else (200, 200, 200)
    cv2.putText(fotograma, texto, (ancho - 330, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1)


def simular(ruta_imagen):
    """
    Procesa una foto como si viniera de la cámara.
    Sirve para probar el sistema sin webcam y para mostrarlo en la defensa.
    """
    fotograma = cv2.imread(ruta_imagen)
    if fotograma is None:
        print(f"No se pudo abrir la imagen {ruta_imagen}")
        return

    nombres, codificaciones = rec.cargar_base()
    if not nombres:
        print("No hay socios cargados.")
        return

    caras = rec.buscar_rostros(fotograma)
    if not caras:
        print("No se detectó ningún rostro en la imagen.")
        return

    for ubicacion, codificacion in caras:
        nombre, distancia = rec.identificar(codificacion, nombres, codificaciones)
        if nombre is None:
            bd.registrar_intento(None, "Rostro no reconocido",
                                 _guardar_foto_intento(fotograma, ubicacion))
            print(f"DESCONOCIDO (distancia {distancia:.2f}) - acceso denegado")
            continue
        decision, etiqueta, detalle = procesar_socio(nombre, fotograma, ubicacion)
        _ultimo_fichaje[nombre] = time.time()
        print(f"{etiqueta:<28}{decision:<13}{detalle}   (distancia {distancia:.2f})")


def iniciar(indice_camara=None):
    """Bucle principal del control de acceso."""
    cerrados = bd.cerrar_registros_abiertos()
    if cerrados:
        print(f"Se cerraron {cerrados} sesiones que habían quedado abiertas de días anteriores.")

    print("Cargando rostros de los socios...")
    nombres, codificaciones = rec.cargar_base()
    if not nombres:
        print("No hay socios cargados. Usá 'python main.py alta' para dar de alta el primero.")
        return
    print(f"{len(nombres)} socios en la base: {', '.join(nombres)}")

    indice = config.INDICE_CAMARA if indice_camara is None else indice_camara
    captura = cv2.VideoCapture(indice)
    if not captura.isOpened():
        print(f"No se pudo abrir la cámara {indice}. Probá con otro índice: python main.py acceso 1")
        return

    print("Control de acceso activo. Presioná Q para salir.")
    contador = 0
    ultimos_resultados = []          # se conservan entre fotogramas para que no titile

    while True:
        exito, fotograma = captura.read()
        if not exito:
            print("No se pudo leer de la cámara.")
            break

        # Solo se analiza 1 de cada N fotogramas: el resto se dibujan con el último resultado
        if contador % config.SALTEAR_FOTOGRAMAS == 0:
            ultimos_resultados = []
            for ubicacion, codificacion in rec.buscar_rostros(fotograma):
                nombre, distancia = rec.identificar(codificacion, nombres, codificaciones)

                if nombre is None:
                    foto = _guardar_foto_intento(fotograma, ubicacion)
                    bd.registrar_intento(None, "Rostro no reconocido", foto)
                    ultimos_resultados.append((ubicacion, "DESCONOCIDO", "No figura en el sistema",
                                               config.COLOR_DESCONOCIDO))
                    continue

                if _en_espera(nombre):
                    # Ya fue procesado hace segundos: se muestra, pero no se registra de nuevo
                    ultimos_resultados.append((ubicacion, nombre, "Registrado recién",
                                               config.COLOR_HABILITADO))
                    continue

                decision, etiqueta, detalle = procesar_socio(nombre, fotograma, ubicacion)
                _ultimo_fichaje[nombre] = time.time()
                print(f"[{datetime.now():%H:%M:%S}] {etiqueta} - {decision} - {detalle} "
                      f"(distancia {distancia:.2f})")
                ultimos_resultados.append((ubicacion, etiqueta, detalle, _color(decision)))
        contador += 1

        for ubicacion, etiqueta, detalle, color in ultimos_resultados:
            rec.dibujar_rostro(fotograma, ubicacion, etiqueta, color, detalle)
        _barra_estado(fotograma)

        cv2.imshow(f"{config.NOMBRE_ESPACIO} - Control de acceso", fotograma)
        if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
            break

    captura.release()
    cv2.destroyAllWindows()
    print("Control de acceso finalizado.")
