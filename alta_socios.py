"""
Alta de socios: registra una persona nueva tomando su foto con la cámara
y cargando su plan, sin tener que copiar archivos a mano en la carpeta.
"""
import os
import re
import unicodedata
from datetime import datetime

import cv2

import base_datos as bd
import config
import reconocimiento as rec


def nombre_valido(nombre):
    """El nombre se usa como nombre de archivo: se limpian los caracteres problemáticos."""
    limpio = re.sub(r'[\\/:*?"<>|]', "", nombre).strip()
    return re.sub(r"\s+", " ", limpio)


def _sin_tildes(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn")


def capturar_foto(nombre, indice_camara=None):
    """
    Abre la cámara para tomar la foto del socio.
    ESPACIO o ENTER saca la foto, C fuerza la captura, Q cancela. Devuelve la ruta o None.
    """
    import camara_util
    indice = config.INDICE_CAMARA if indice_camara is None else indice_camara
    captura = camara_util.abrir_camara(indice)
    if captura is None or not captura.isOpened():
        print(f"No se pudo abrir ninguna cámara disponible (probado índice {indice}).")
        return None

    os.makedirs(config.CARPETA_SOCIOS, exist_ok=True)
    ruta = os.path.join(config.CARPETA_SOCIOS, f"{nombre}.jpg")
    print("\nMirá a la cámara.")
    print("  - ESPACIO o ENTER: capturar foto (cuando detecte tu rostro)")
    print("  - C: forzar captura en cualquier momento")
    print("  - Q: cancelar\n")

    guardada = None
    while True:
        exito, fotograma = captura.read()
        if not exito or fotograma is None:
            break

        vista = fotograma.copy()
        caras = rec.buscar_rostros(fotograma)
        for ubicacion, _ in caras:
            arriba, derecha, abajo, izquierda = ubicacion
            cv2.rectangle(vista, (izquierda, arriba), (derecha, abajo), config.COLOR_HABILITADO, 2)

        if len(caras) == 1:
            estado = "Rostro detectado - ESPACIO / ENTER para capturar"
            color = config.COLOR_HABILITADO
        elif len(caras) > 1:
            estado = f"Se detectan {len(caras)} rostros (o presiona 'C' para forzar)"
            color = config.COLOR_ADVERTENCIA
        else:
            estado = "Buscando rostro... (o presiona 'C' para forzar captura)"
            color = config.COLOR_ADVERTENCIA

        # Barra superior con nombre
        cv2.rectangle(vista, (0, 0), (vista.shape[1], 36), (30, 30, 30), cv2.FILLED)
        cv2.putText(vista, f"Alta de socio: {_sin_tildes(nombre)}", (12, 24),
                    cv2.FONT_HERSHEY_DUPLEX, 0.55, (255, 255, 255), 1)

        # Barra inferior con estado e instrucciones
        cv2.rectangle(vista, (0, vista.shape[0] - 44), (vista.shape[1], vista.shape[0]), (20, 20, 20), cv2.FILLED)
        cv2.putText(vista, estado, (12, vista.shape[0] - 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, color, 1)
        cv2.putText(vista, "ESPACIO/ENTER: Capturar | C: Forzar | Q: Salir", (12, vista.shape[0] - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180, 180, 180), 1)

        cv2.imshow("Alta de socio - Coworking", vista)
        tecla = cv2.waitKey(1) & 0xFF

        if tecla in (ord(" "), 13, 10):
            if len(caras) == 1:
                cv2.imwrite(ruta, fotograma)
                guardada = ruta
                break
            else:
                print(f"[!] Rostros detectados: {len(caras)}. Podés presionar 'C' para forzar la foto si tu rostro ya está centrado.")
        elif tecla in (ord("c"), ord("C")):
            cv2.imwrite(ruta, fotograma)
            guardada = ruta
            print("[+] Foto capturada mediante forzado manual.")
            break
        elif tecla in (ord("q"), ord("Q"), 27):
            print("Captura cancelada por el usuario.")
            break

    captura.release()
    cv2.destroyAllWindows()
    return guardada


def alta_interactiva():
    """Pide los datos por consola y da de alta al socio."""
    print("\n--- ALTA DE SOCIO ---")
    nombre = nombre_valido(input("Nombre y apellido: "))
    if not nombre:
        print("El nombre no puede quedar vacío.")
        return
    if bd.obtener_socio(nombre):
        print(f"Ya existe un socio llamado {nombre}.")
        return

    print("\nPlanes disponibles:")
    claves = list(config.PLANES)
    for i, clave in enumerate(claves, start=1):
        plan = config.PLANES[clave]
        horas = "ilimitadas" if plan["horas_incluidas"] is None else f"{plan['horas_incluidas']} h/mes"
        print(f"  {i}. {plan['nombre']:28} {horas:14} "
              f"({plan['hora_desde']} a {plan['hora_hasta']} hs)")

    eleccion = input(f"\nNúmero de plan [1-{len(claves)}]: ").strip()
    if not eleccion.isdigit() or not 1 <= int(eleccion) <= len(claves):
        print("Opción inválida.")
        return
    plan = claves[int(eleccion) - 1]

    dias = input("Días de vigencia [30]: ").strip()
    dias = int(dias) if dias.isdigit() else 30

    foto = capturar_foto(nombre)
    if not foto:
        print("No se tomó la foto. Alta cancelada.")
        return

    if rec.codificar_foto(foto) is None:
        os.remove(foto)
        print("No se pudo detectar el rostro en la foto. Probá de nuevo con mejor luz.")
        return

    bd.alta_socio(nombre, plan, dias, foto)
    rec.cargar_base(forzar=True)        # actualizar el caché con el socio nuevo
    print(f"\n[OK] {nombre} dado de alta con {config.PLANES[plan]['nombre']} "
          f"por {dias} días.\n")


def alta_desde_carpeta():
    """
    Da de alta a todas las fotos que estén en la carpeta Socios y todavía no
    figuren en la base de datos. Útil para cargar varias personas de una vez.
    """
    if not os.path.isdir(config.CARPETA_SOCIOS):
        print(f"No existe la carpeta {config.CARPETA_SOCIOS}")
        return

    claves = list(config.PLANES)
    nuevos = 0
    for archivo in sorted(os.listdir(config.CARPETA_SOCIOS)):
        if not archivo.lower().endswith(rec.EXTENSIONES):
            continue
        nombre = os.path.splitext(archivo)[0]
        if bd.obtener_socio(nombre):
            continue

        print(f"\nFoto sin socio asociado: {nombre}")
        for i, clave in enumerate(claves, start=1):
            print(f"  {i}. {config.PLANES[clave]['nombre']}")
        eleccion = input(f"Plan para {nombre} [1-{len(claves)}, Enter para saltear]: ").strip()
        if not eleccion.isdigit() or not 1 <= int(eleccion) <= len(claves):
            continue
        bd.alta_socio(nombre, claves[int(eleccion) - 1], 30,
                      os.path.join(config.CARPETA_SOCIOS, archivo))
        nuevos += 1
        print(f"  [OK] {nombre} dado de alta")

    if nuevos:
        rec.cargar_base(forzar=True)
    print(f"\n{nuevos} socios dados de alta.")
