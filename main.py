"""
Sistema de control de acceso y consumo de horas para un espacio de coworking
mediante reconocimiento facial.

Ingeniería del Conocimiento - TP N° 3 (2° Proyecto: Sistema de Asistencias)
Universidad del Aconcagua - Licenciatura en Informática y Desarrollo de Software

Uso:
    python main.py                 menú interactivo
    python main.py web             interfaz web profesional (dashboard + kiosco)
    python main.py acceso          control de acceso en tiempo real (cámara)
    python main.py alta            dar de alta un socio con la cámara
    python main.py importar        dar de alta las fotos ya cargadas en Socios/
    python main.py panel           quiénes están adentro ahora
    python main.py consumo         consumo y facturación del mes
    python main.py ocupacion       ocupación por franja horaria
    python main.py historial       últimos accesos
    python main.py rechazados      accesos rechazados y desconocidos
    python main.py padron          padrón de socios
    python main.py reglas          base de conocimiento del sistema
    python main.py demo            cargar datos de prueba
"""
import sys

import config

OPCIONES = [
    ("W", "Abrir Interfaz Web Profesional (Dashboard + Kiosco)", "web"),
    ("1", "Iniciar control de acceso (cámara)", "acceso"),
    ("2", "Dar de alta un socio", "alta"),
    ("3", "Ver quién está adentro ahora", "panel"),
    ("4", "Consumo y facturación del mes", "consumo"),
    ("5", "Ocupación por franja horaria", "ocupacion"),
    ("6", "Historial de accesos", "historial"),
    ("7", "Accesos rechazados", "rechazados"),
    ("8", "Padrón de socios", "padron"),
    ("9", "Ver la base de conocimiento", "reglas"),
    ("0", "Salir", "salir"),
]


def ejecutar(accion, extra=None):
    # Los módulos se importan acá adentro para que el menú abra rápido
    # y para que un reporte no tenga que esperar la carga de OpenCV.
    if accion == "web":
        import app
        print(f"\n========================================================")
        print(f"  {config.NOMBRE_ESPACIO} - PANEL WEB INICIADO")
        print(f"  Abrí tu navegador en: http://127.0.0.1:5000")
        print(f"========================================================\n")
        app.app.run(host="0.0.0.0", port=5000, debug=False)
    elif accion == "acceso":
        import control_acceso
        control_acceso.iniciar(int(extra) if extra and extra.isdigit() else None)
    elif accion == "alta":
        import alta_socios
        alta_socios.alta_interactiva()
    elif accion == "importar":
        import alta_socios
        alta_socios.alta_desde_carpeta()
    elif accion == "simular":
        import control_acceso
        if not extra:
            print("Indicá la foto: python main.py simular \"Socios/Jerry Seinfeld.jpg\"")
            return
        control_acceso.simular(extra)
    elif accion == "demo":
        import datos_demo
        datos_demo.cargar()
    else:
        import reportes
        acciones = {
            "panel": reportes.panel_en_vivo,
            "consumo": lambda: reportes.consumo_por_socio(exportar=extra == "csv"),
            "ocupacion": lambda: reportes.ocupacion_por_hora(exportar=extra == "csv"),
            "historial": lambda: reportes.historial_accesos(exportar=extra == "csv"),
            "rechazados": lambda: reportes.accesos_rechazados(exportar=extra == "csv"),
            "padron": lambda: reportes.padron_socios(exportar=extra == "csv"),
            "reglas": reportes.mostrar_reglas,
        }
        if accion not in acciones:
            print(f"Acción desconocida: {accion}")
            print(__doc__)
            return
        acciones[accion]()


def menu():
    while True:
        print(f"\n{'=' * 56}")
        print(f"  {config.NOMBRE_ESPACIO} - SISTEMA DE CONTROL DE ACCESO")
        print("=" * 56)
        for tecla, texto, _ in OPCIONES:
            print(f"  {tecla}. {texto}")

        eleccion = input("\nOpción: ").strip()
        accion = next((a for t, _, a in OPCIONES if t.upper() == eleccion.upper()), None)

        if accion == "salir":
            print("Hasta luego.\n")
            break
        if accion is None:
            print("Opción inválida.")
            continue
        try:
            ejecutar(accion)
        except KeyboardInterrupt:
            print("\nOperación cancelada.")
        except Exception as e:
            print(f"\nError: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        ejecutar(sys.argv[1].lower(), sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        menu()
