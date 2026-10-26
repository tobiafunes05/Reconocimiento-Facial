"""
Carga datos de prueba para poder mostrar el sistema funcionando sin tener
que esperar semanas de uso real.

Crea socios con situaciones distintas (plan vigente, plan vencido, bolsa
agotada, pocas horas) para que se puedan demostrar todas las reglas de acceso,
y genera un historial de accesos del último mes para los reportes.
"""
import os
import random
from datetime import datetime, timedelta

import base_datos as bd
import config

# Cada socio de prueba cubre una situación distinta del motor de reglas.
# 'horas_objetivo' son las horas que debe acumular en el mes en curso: ese número
# es el que hace que al socio le dispare una regla u otra al intentar entrar.
SOCIOS_DEMO = [
    # (nombre,              plan,          días vigencia, horas objetivo del mes)
    ("Jerry Seinfeld",      "libre",         25,  32),   # todo en regla
    ("Elaine Benes",        "bolsa",         18,  36),   # quedan 4 h -> R7 aviso
    ("Cosmo Kramer",        "bolsa",         12,  47),   # bolsa agotada -> R6 excedente
    ("George Constanza",    "diurno",        20,  24),   # solo de 8 a 17 -> R3 según la hora
    ("Carl Sagan",          "libre",          5,  28),   # plan por vencer -> R8 aviso
    ("Michio Kaku",         "pase_diario",   -3,   6),   # plan vencido -> R2 rechazo
    ("Neil deGrasse Tyson", "invitado",       1,   1.5), # invitado, máx 2 h
]


def _fotos_disponibles():
    if not os.path.isdir(config.CARPETA_SOCIOS):
        return set()
    return {os.path.splitext(f)[0] for f in os.listdir(config.CARPETA_SOCIOS)
            if f.lower().endswith((".jpg", ".jpeg", ".png"))}


def cargar(con_historial=True):
    fotos = _fotos_disponibles()
    creados, sin_foto = 0, []

    for nombre, plan, dias, _horas in SOCIOS_DEMO:
        if bd.obtener_socio(nombre):
            continue
        if nombre not in fotos:
            sin_foto.append(nombre)
        ruta = os.path.join(config.CARPETA_SOCIOS, f"{nombre}.jpg") if nombre in fotos else None
        bd.alta_socio(nombre, plan, dias, ruta)
        creados += 1

    print(f"[OK] {creados} socios de prueba cargados.")
    if sin_foto:
        print(f"  Sin foto en la carpeta Socios/: {', '.join(sin_foto)}")
        print("  (Figuran en el padrón, pero la cámara no los va a reconocer.)")

    if con_historial:
        generados = _generar_historial()
        print(f"[OK] {generados} accesos históricos generados para los reportes.")

    print("\nProbá ahora:")
    print("  python main.py padron")
    print("  python main.py consumo")
    print("  python main.py ocupacion\n")


def _dias_habiles_del_mes():
    """Días hábiles del mes en curso que ya transcurrieron, incluido hoy."""
    hoy = datetime.now()
    dias = []
    for numero in range(1, hoy.day + 1):
        fecha = hoy.replace(day=numero, hour=0, minute=0, second=0, microsecond=0)
        if fecha.weekday() < 5:
            dias.append(fecha)
    return dias


def _sesiones_para(objetivo, dias_disponibles, plan, aleatorio):
    """
    Reparte 'objetivo' horas en varias sesiones ubicadas en días distintos,
    siempre dentro de la franja horaria que permite el plan.
    Devuelve [(entrada, salida, horas)].
    """
    margen = plan["hora_hasta"] - plan["hora_desde"]
    max_sesion = min(8.0, margen - 0.5)
    if max_sesion <= 0.5 or not dias_disponibles:
        return []

    # Un invitado hace sesiones cortas; el resto, jornadas normales
    if plan["horas_incluidas"] is not None and plan["horas_incluidas"] <= 2:
        max_sesion = min(max_sesion, plan["horas_incluidas"])

    dias = aleatorio.sample(dias_disponibles, min(len(dias_disponibles),
                                                  max(1, int(objetivo / (max_sesion * 0.65)) + 1)))
    dias.sort()

    sesiones, restante = [], objetivo
    for i, dia in enumerate(dias):
        quedan_dias = len(dias) - i
        if restante <= 0.4:
            break
        # Repartir lo que falta entre los días que quedan, con algo de variación
        objetivo_dia = restante / quedan_dias * aleatorio.uniform(0.85, 1.15)
        horas = round(max(0.5, min(objetivo_dia, max_sesion, restante)), 2)

        ultima_entrada = plan["hora_hasta"] - horas
        if ultima_entrada < plan["hora_desde"]:
            continue
        hora_entrada = aleatorio.uniform(plan["hora_desde"], min(ultima_entrada,
                                                                 plan["hora_desde"] + 4))
        entrada = dia + timedelta(hours=hora_entrada)
        entrada = entrada.replace(minute=aleatorio.choice([0, 15, 30, 45]), second=0)
        salida = entrada + timedelta(hours=horas)
        if salida.hour >= plan["hora_hasta"] and salida.minute > 0:
            salida = salida.replace(hour=plan["hora_hasta"], minute=0)
            horas = round((salida - entrada).total_seconds() / 3600, 2)
        if horas <= 0.4:
            continue

        sesiones.append((entrada, salida, horas))
        restante -= horas
    return sesiones


def _generar_historial():
    """
    Genera los accesos del mes en curso para que cada socio llegue a sus horas
    objetivo, respetando la franja horaria de su plan y calculando el excedente
    de los planes con bolsa de horas.
    """
    objetivos = {nombre: horas for nombre, _p, _d, horas in SOCIOS_DEMO}

    with bd.conectar() as con:
        if con.execute("SELECT COUNT(*) FROM registros").fetchone()[0]:
            return 0

        socios = con.execute("SELECT id, nombre, plan FROM socios").fetchall()
        if not socios:
            return 0

        dias = _dias_habiles_del_mes()
        if not dias:
            print("  (El mes recién empieza: no hay días hábiles para generar historial.)")
            return 0

        # Si el mes está empezando, no entran todas las horas: se escalan los objetivos
        capacidad = len(dias) * 8.0
        mayor = max(objetivos.values())
        factor = min(1.0, capacidad / mayor) if mayor else 1.0
        if factor < 1.0:
            print(f"  (Mes en curso corto: los objetivos se escalaron al {factor:.0%}.)")

        aleatorio = random.Random(42)    # reproducible: los reportes dan igual en cada corrida
        generados = 0

        for socio in socios:
            plan = config.PLANES.get(socio["plan"], config.PLANES["libre"])
            objetivo = objetivos.get(socio["nombre"], 20) * factor
            acumulado = 0.0

            for entrada, salida, horas in _sesiones_para(objetivo, dias, plan, aleatorio):
                excedente = 0.0
                incluidas = plan["horas_incluidas"]
                if incluidas is not None:
                    disponibles = max(incluidas - acumulado, 0)
                    excedente = round(max(horas - disponibles, 0), 2)
                acumulado += horas

                con.execute(
                    "INSERT INTO registros (socio_id, nombre, entrada, salida, horas, excedente) "
                    "VALUES (?,?,?,?,?,?)",
                    (socio["id"], socio["nombre"],
                     entrada.strftime("%Y-%m-%d %H:%M:%S"),
                     salida.strftime("%Y-%m-%d %H:%M:%S"), horas, excedente))
                generados += 1

            con.execute("UPDATE socios SET horas_usadas=? WHERE id=?",
                        (round(acumulado, 2), socio["id"]))

        # Una reserva de sala para hoy, para mostrar la regla R9
        con.execute(
            "INSERT INTO reservas (socio_id, sala, fecha, hora_desde, hora_hasta) VALUES (?,?,?,?,?)",
            (socios[0]["id"], "Sala de reuniones 1",
             datetime.now().strftime("%Y-%m-%d"), "15:00", "16:30"))

    return generados


if __name__ == "__main__":
    cargar()
