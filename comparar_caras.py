"""
Script de comparación de dos rostros.

Es el primer script que pide el enunciado: carga dos imágenes, localiza los
rostros, los codifica y determina si pertenecen a la misma persona, mostrando
el resultado y la distancia entre ambos.

Uso:
    python comparar_caras.py FotoA.jpg FotoB.jpg
    python comparar_caras.py FotoA.jpg FotoB.jpg --sin-ventana
"""
import sys

import cv2
import numpy as np
try:
    import face_recognition as fr
except ImportError:
    fr = None

import config
import reconocimiento as rec


def comparar(ruta_a, ruta_b, tolerancia=None, mostrar=True):
    """Compara dos imágenes. Devuelve (coincide, distancia)."""
    tolerancia = config.TOLERANCIA if tolerancia is None else tolerancia

    if fr is not None:
        # load_image_file devuelve la imagen ya en RGB, que es lo que espera face_recognition
        foto_control = fr.load_image_file(ruta_a)
        foto_prueba = fr.load_image_file(ruta_b)

        lugares_a = fr.face_locations(foto_control)
        lugares_b = fr.face_locations(foto_prueba)
        if not lugares_a:
            print(f"No se detectó ningún rostro en {ruta_a}")
            return None, None
        if not lugares_b:
            print(f"No se detectó ningún rostro en {ruta_b}")
            return None, None

        cara_a = fr.face_encodings(foto_control, lugares_a)[0]
        cara_b = fr.face_encodings(foto_prueba, lugares_b)[0]
        distancia = float(fr.face_distance([cara_a], cara_b)[0])
        lugar_a = lugares_a[0]
        lugar_b = lugares_b[0]
        vista_a = cv2.cvtColor(foto_control, cv2.COLOR_RGB2BGR)
        vista_b = cv2.cvtColor(foto_prueba, cv2.COLOR_RGB2BGR)
    else:
        # Fallback usando OpenCV / Haar Cascades
        bgr_a = cv2.imread(ruta_a)
        bgr_b = cv2.imread(ruta_b)
        if bgr_a is None or bgr_b is None:
            print("Error al leer una de las imágenes")
            return None, None
        caras_a = rec.buscar_rostros(bgr_a)
        caras_b = rec.buscar_rostros(bgr_b)
        if not caras_a:
            print(f"No se detectó ningún rostro en {ruta_a}")
            return None, None
        if not caras_b:
            print(f"No se detectó ningún rostro en {ruta_b}")
            return None, None
        lugar_a, cara_a = caras_a[0]
        lugar_b, cara_b = caras_b[0]
        distancia = float(0.5 * cv2.norm(np.array(cara_a) - np.array(cara_b)))
        vista_a = bgr_a.copy()
        vista_b = bgr_b.copy()

    coincide = distancia <= tolerancia

    print(f"\nFoto control : {ruta_a}")
    print(f"Foto prueba  : {ruta_b}")
    print(f"Distancia    : {distancia:.4f}   (tolerancia {tolerancia})")
    print(f"Resultado    : {'ES LA MISMA PERSONA' if coincide else 'SON PERSONAS DISTINTAS'}\n")

    if mostrar:
        color = config.COLOR_HABILITADO if coincide else config.COLOR_RECHAZADO
        for vista, lugar in ((vista_a, lugar_a), (vista_b, lugar_b)):
            arriba, derecha, abajo, izquierda = lugar
            cv2.rectangle(vista, (izquierda, arriba), (derecha, abajo), color, 2)

        texto = f"{'COINCIDE' if coincide else 'NO COINCIDE'}  dist={distancia:.2f}"
        cv2.putText(vista_b, texto, (20, 40), cv2.FONT_HERSHEY_DUPLEX, 0.8, color, 2)

        cv2.imshow("Foto control", vista_a)
        cv2.imshow("Foto prueba", vista_b)
        print("Presioná cualquier tecla sobre la ventana para cerrar.")
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    return coincide, distancia


if __name__ == "__main__":
    argumentos = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(argumentos) != 2:
        print(__doc__)
        sys.exit(1)
    comparar(argumentos[0], argumentos[1], mostrar="--sin-ventana" not in sys.argv)
