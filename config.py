"""
Configuración central del sistema de control de acceso del coworking.
Todos los parámetros ajustables del sistema están en este archivo.
"""
import os

# ---------------- Datos del espacio ----------------
NOMBRE_ESPACIO = "Coworking Aconcagua"
AFORO_MAXIMO = 25                  # cantidad máxima de personas adentro al mismo tiempo

# ---------------- Rutas ----------------
CARPETA_BASE = os.path.dirname(os.path.abspath(__file__))
CARPETA_SOCIOS = os.path.join(CARPETA_BASE, "Socios")          # fotos de los socios
CARPETA_INTENTOS = os.path.join(CARPETA_BASE, "intentos")      # fotos de caras desconocidas
CARPETA_REPORTES = os.path.join(CARPETA_BASE, "reportes")      # CSV exportados
RUTA_DB = os.path.join(CARPETA_BASE, "datos", "coworking.db")
RUTA_CACHE = os.path.join(CARPETA_BASE, "datos", "codificaciones.pkl")

# ---------------- Reconocimiento facial ----------------
# Tolerancia de comparación: cuanto MÁS BAJA, más estricto el sistema.
# 0.6 es el valor por defecto de face_recognition. 0.5 reduce los falsos positivos.
TOLERANCIA = 0.50

# Procesar 1 de cada N fotogramas (acelera el video en tiempo real)
SALTEAR_FOTOGRAMAS = 3
# Reducir el fotograma a 1/4 antes de procesarlo (el reconocimiento es mucho más rápido)
ESCALA_PROCESO = 0.25
# Modelo de detección: "hog" (rápido, CPU) o "cnn" (más preciso, necesita GPU)
MODELO_DETECCION = "hog"

# Segundos que el sistema ignora a una persona ya fichada,
# para que no registre varias veces seguidas mientras está frente a la cámara.
SEGUNDOS_ESPERA = 20

# Índice de la cámara web (0 es la cámara por defecto)
INDICE_CAMARA = 0

# ---------------- Reglas de los planes ----------------
# Cada plan define cómo se controla el acceso y cómo se cobra.
PLANES = {
    "libre": {
        "nombre": "Plan Libre",
        "descripcion": "Acceso ilimitado en horario completo",
        "horas_incluidas": None,            # None = sin límite de horas
        "hora_desde": 7, "hora_hasta": 23,
        "precio_hora_excedente": 0,
    },
    "bolsa": {
        "nombre": "Plan por Bolsa de Horas",
        "descripcion": "Cantidad de horas mensuales contratadas",
        "horas_incluidas": 40,
        "hora_desde": 7, "hora_hasta": 23,
        "precio_hora_excedente": 3500,
    },
    "diurno": {
        "nombre": "Plan Diurno",
        "descripcion": "Acceso de 8 a 17 horas",
        "horas_incluidas": None,
        "hora_desde": 8, "hora_hasta": 17,
        "precio_hora_excedente": 0,
    },
    "pase_diario": {
        "nombre": "Pase Diario",
        "descripcion": "Un día de acceso",
        "horas_incluidas": 9,
        "hora_desde": 8, "hora_hasta": 20,
        "precio_hora_excedente": 4000,
    },
    "invitado": {
        "nombre": "Invitado",
        "descripcion": "Visita acompañada, máximo 2 horas",
        "horas_incluidas": 2,
        "hora_desde": 9, "hora_hasta": 19,
        "precio_hora_excedente": 0,
    },
}

# Avisos preventivos
DIAS_AVISO_VENCIMIENTO = 7      # avisar si al plan le quedan menos de X días
HORAS_AVISO_BOLSA = 5           # avisar si quedan menos de X horas en la bolsa

# ---------------- Interfaz ----------------
COLOR_HABILITADO = (0, 200, 0)      # verde  (BGR de OpenCV)
COLOR_ADVERTENCIA = (0, 190, 255)   # ámbar
COLOR_RECHAZADO = (0, 0, 230)       # rojo
COLOR_DESCONOCIDO = (120, 120, 120) # gris
