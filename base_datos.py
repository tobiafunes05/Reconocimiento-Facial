"""
Base de datos del sistema (SQLite).

Tablas:
    socios     -> legajo de cada persona: plan contratado, vencimiento y foto
    registros  -> cada entrada y salida, con las horas consumidas
    reservas   -> reservas de la sala de reuniones
    intentos   -> accesos rechazados y caras desconocidas
"""
import csv
import os
import sqlite3
from datetime import datetime, timedelta

import config


def conectar():
    """Abre la conexión y crea las tablas si no existen."""
    os.makedirs(os.path.dirname(config.RUTA_DB), exist_ok=True)
    con = sqlite3.connect(config.RUTA_DB)
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE IF NOT EXISTS socios (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre          TEXT NOT NULL UNIQUE,
            plan            TEXT NOT NULL,
            vence           TEXT NOT NULL,       -- 'YYYY-MM-DD'
            horas_usadas    REAL DEFAULT 0,      -- horas consumidas en el mes
            mes_periodo     TEXT,                -- 'YYYY-MM' del período en curso
            foto            TEXT,
            activo          INTEGER DEFAULT 1,
            alta            TEXT
        );
        CREATE TABLE IF NOT EXISTS registros (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            socio_id        INTEGER NOT NULL,
            nombre          TEXT NOT NULL,
            entrada         TEXT NOT NULL,       -- 'YYYY-MM-DD HH:MM:SS'
            salida          TEXT,
            horas           REAL,
            excedente       REAL DEFAULT 0,      -- horas fuera de la bolsa contratada
            FOREIGN KEY (socio_id) REFERENCES socios(id)
        );
        CREATE TABLE IF NOT EXISTS reservas (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            socio_id        INTEGER NOT NULL,
            sala            TEXT NOT NULL,
            fecha           TEXT NOT NULL,       -- 'YYYY-MM-DD'
            hora_desde      TEXT NOT NULL,       -- 'HH:MM'
            hora_hasta      TEXT NOT NULL,
            FOREIGN KEY (socio_id) REFERENCES socios(id)
        );
        CREATE TABLE IF NOT EXISTS intentos (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            momento         TEXT NOT NULL,
            nombre          TEXT,                -- NULL si la cara es desconocida
            motivo          TEXT NOT NULL,
            foto            TEXT
        );
    """)
    return con


def _ahora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------- Socios ----------------
def alta_socio(nombre, plan, dias_vigencia=30, foto=None):
    vence = (datetime.now() + timedelta(days=dias_vigencia)).strftime("%Y-%m-%d")
    with conectar() as con:
        cur = con.execute(
            "INSERT INTO socios (nombre, plan, vence, mes_periodo, foto, alta) VALUES (?,?,?,?,?,?)",
            (nombre, plan, vence, datetime.now().strftime("%Y-%m"), foto, _ahora()))
        return cur.lastrowid


def obtener_socio(nombre):
    with conectar() as con:
        return con.execute("SELECT * FROM socios WHERE nombre = ?", (nombre,)).fetchone()


def listar_socios(solo_activos=True):
    consulta = "SELECT * FROM socios"
    if solo_activos:
        consulta += " WHERE activo = 1"
    with conectar() as con:
        return con.execute(consulta + " ORDER BY nombre").fetchall()


def renovar_plan(nombre, plan=None, dias_vigencia=30):
    """Renueva la vigencia y reinicia la bolsa de horas del período."""
    vence = (datetime.now() + timedelta(days=dias_vigencia)).strftime("%Y-%m-%d")
    with conectar() as con:
        if plan:
            con.execute("UPDATE socios SET plan=?, vence=?, horas_usadas=0, mes_periodo=? WHERE nombre=?",
                        (plan, vence, datetime.now().strftime("%Y-%m"), nombre))
        else:
            con.execute("UPDATE socios SET vence=?, horas_usadas=0, mes_periodo=? WHERE nombre=?",
                        (vence, datetime.now().strftime("%Y-%m"), nombre))


def reiniciar_periodo_si_cambio_mes(socio):
    """Si cambió el mes, la bolsa de horas vuelve a cero."""
    mes_actual = datetime.now().strftime("%Y-%m")
    if socio["mes_periodo"] != mes_actual:
        with conectar() as con:
            con.execute("UPDATE socios SET horas_usadas=0, mes_periodo=? WHERE id=?",
                        (mes_actual, socio["id"]))
        return obtener_socio(socio["nombre"])
    return socio


def baja_socio(nombre, borrar_foto=True):
    """Elimina definitivamente al socio, sus registros, reservas y su foto."""
    with conectar() as con:
        socio = con.execute("SELECT * FROM socios WHERE nombre=?", (nombre,)).fetchone()
        if not socio:
            return 0
        socio_id = socio["id"]
        con.execute("DELETE FROM registros WHERE socio_id=?", (socio_id,))
        con.execute("DELETE FROM reservas WHERE socio_id=?", (socio_id,))
        filas = con.execute("DELETE FROM socios WHERE id=?", (socio_id,)).rowcount

    # Eliminar foto de la carpeta Socios si existe
    if borrar_foto and os.path.isdir(config.CARPETA_SOCIOS):
        for archivo in os.listdir(config.CARPETA_SOCIOS):
            nom_arch, _ = os.path.splitext(archivo)
            if nom_arch.lower() == nombre.lower():
                try:
                    os.remove(os.path.join(config.CARPETA_SOCIOS, archivo))
                except Exception as e:
                    print(f"[!] Error al eliminar foto de {nombre}: {e}")

    return filas


# ---------------- Registros de acceso ----------------
def registro_abierto(socio_id):
    """Devuelve el registro sin salida (la persona está adentro) o None."""
    with conectar() as con:
        return con.execute(
            "SELECT * FROM registros WHERE socio_id=? AND salida IS NULL ORDER BY entrada DESC LIMIT 1",
            (socio_id,)).fetchone()


def registrar_entrada(socio_id, nombre):
    with conectar() as con:
        cur = con.execute("INSERT INTO registros (socio_id, nombre, entrada) VALUES (?,?,?)",
                          (socio_id, nombre, _ahora()))
        return cur.lastrowid


def registrar_salida(id_registro, horas, excedente=0.0):
    with conectar() as con:
        con.execute("UPDATE registros SET salida=?, horas=?, excedente=? WHERE id=?",
                    (_ahora(), round(horas, 2), round(excedente, 2), id_registro))


def sumar_horas_usadas(socio_id, horas):
    with conectar() as con:
        con.execute("UPDATE socios SET horas_usadas = horas_usadas + ? WHERE id=?",
                    (round(horas, 2), socio_id))


def personas_adentro():
    """Lista de quienes están adentro ahora, con la hora de entrada."""
    with conectar() as con:
        return con.execute(
            "SELECT r.*, s.plan FROM registros r JOIN socios s ON s.id = r.socio_id "
            "WHERE r.salida IS NULL ORDER BY r.entrada").fetchall()


def cantidad_adentro():
    with conectar() as con:
        return con.execute("SELECT COUNT(*) FROM registros WHERE salida IS NULL").fetchone()[0]


def cerrar_registros_abiertos():
    """Cierra las sesiones que quedaron abiertas de días anteriores (olvidos de check-out)."""
    hoy = datetime.now().strftime("%Y-%m-%d")
    with conectar() as con:
        abiertos = con.execute("SELECT * FROM registros WHERE salida IS NULL AND entrada < ?",
                               (hoy + " 00:00:00",)).fetchall()
        for r in abiertos:
            entrada = datetime.strptime(r["entrada"], "%Y-%m-%d %H:%M:%S")
            # Se cierra al final de ese día y se marca como cierre automático
            cierre = entrada.replace(hour=23, minute=59, second=0)
            horas = max((cierre - entrada).total_seconds() / 3600, 0)
            con.execute("UPDATE registros SET salida=?, horas=? WHERE id=?",
                        (cierre.strftime("%Y-%m-%d %H:%M:%S"), round(horas, 2), r["id"]))
        return len(abiertos)


# ---------------- Reservas ----------------
def crear_reserva(socio_id, sala, fecha, hora_desde, hora_hasta):
    with conectar() as con:
        cur = con.execute(
            "INSERT INTO reservas (socio_id, sala, fecha, hora_desde, hora_hasta) VALUES (?,?,?,?,?)",
            (socio_id, sala, fecha, hora_desde, hora_hasta))
        return cur.lastrowid


def reserva_de_hoy(socio_id):
    hoy = datetime.now().strftime("%Y-%m-%d")
    with conectar() as con:
        return con.execute(
            "SELECT * FROM reservas WHERE socio_id=? AND fecha=? ORDER BY hora_desde LIMIT 1",
            (socio_id, hoy)).fetchone()


# ---------------- Intentos rechazados ----------------
def registrar_intento(nombre, motivo, foto=None):
    with conectar() as con:
        con.execute("INSERT INTO intentos (momento, nombre, motivo, foto) VALUES (?,?,?,?)",
                    (_ahora(), nombre, motivo, foto))


def listar_intentos(limite=50):
    with conectar() as con:
        return con.execute("SELECT * FROM intentos ORDER BY momento DESC LIMIT ?", (limite,)).fetchall()


# ---------------- Exportación ----------------
def exportar_csv(filas, nombre_archivo, encabezados=None):
    """Guarda una lista de filas en un CSV dentro de la carpeta reportes."""
    os.makedirs(config.CARPETA_REPORTES, exist_ok=True)
    ruta = os.path.join(config.CARPETA_REPORTES, nombre_archivo)
    filas = list(filas)
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        escritor = csv.writer(f)
        if filas:
            escritor.writerow(encabezados or filas[0].keys())
            for fila in filas:
                escritor.writerow(list(fila))
        elif encabezados:
            escritor.writerow(encabezados)
    return ruta
