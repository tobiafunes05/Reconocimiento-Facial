"""
Reportes del sistema: consumo por socio, facturación estimada,
ocupación por franja horaria e historial de accesos rechazados.
Todos se pueden exportar a CSV.
"""
import sys
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import base_datos as bd
import config
import reglas


def _mes_actual():
    return datetime.now().strftime("%Y-%m")


def _linea(ancho=74):
    return "=" * ancho


# ---------------- Panel en vivo ----------------
def panel_en_vivo():
    adentro = bd.personas_adentro()
    print(f"\n{_linea()}")
    print(f"  {config.NOMBRE_ESPACIO} - EN ESTE MOMENTO")
    print(_linea())
    print(f"  Ocupación: {len(adentro)}/{config.AFORO_MAXIMO} personas"
          f"   ({len(adentro) * 100 // config.AFORO_MAXIMO}% del aforo)\n")
    if not adentro:
        print("  No hay nadie adentro.\n")
        return
    print(f"  {'SOCIO':<26}{'PLAN':<14}{'DESDE':<10}{'HACE'}")
    print(f"  {'-' * 66}")
    for r in adentro:
        entrada = datetime.strptime(r["entrada"], "%Y-%m-%d %H:%M:%S")
        horas = (datetime.now() - entrada).total_seconds() / 3600
        print(f"  {r['nombre']:<26}{config.PLANES[r['plan']]['nombre'][:13]:<14}"
              f"{entrada.strftime('%H:%M'):<10}{horas:.1f} h")
    print()


# ---------------- Consumo y facturación ----------------
def consumo_por_socio(mes=None, exportar=False):
    mes = mes or _mes_actual()
    with bd.conectar() as con:
        filas = con.execute("""
            SELECT s.nombre, s.plan, s.vence,
                   COUNT(r.id)                AS sesiones,
                   IFNULL(SUM(r.horas), 0)    AS horas,
                   IFNULL(SUM(r.excedente),0) AS excedente
            FROM socios s
            LEFT JOIN registros r ON r.socio_id = s.id
                 AND strftime('%Y-%m', r.entrada) = ? AND r.salida IS NOT NULL
            WHERE s.activo = 1
            GROUP BY s.id ORDER BY horas DESC""", (mes,)).fetchall()

    print(f"\n{_linea()}")
    print(f"  CONSUMO POR SOCIO - {mes}")
    print(_linea())
    print(f"  {'SOCIO':<24}{'PLAN':<22}{'SES.':>5}{'HORAS':>8}{'EXCED.':>8}{'A FACTURAR':>12}")
    print(f"  {'-' * 79}")

    total = 0
    exportables = []
    for f in filas:
        plan = config.PLANES.get(f["plan"], {})
        importe = f["excedente"] * plan.get("precio_hora_excedente", 0)
        total += importe
        incluidas = plan.get("horas_incluidas")
        etiqueta_plan = plan.get("nombre", f["plan"])
        if incluidas:
            etiqueta_plan += f" ({f['horas']:.0f}/{incluidas}h)"
        print(f"  {f['nombre']:<24}{etiqueta_plan[:21]:<22}{f['sesiones']:>5}"
              f"{f['horas']:>8.1f}{f['excedente']:>8.1f}{importe:>12,.0f}")
        exportables.append([f["nombre"], plan.get("nombre", f["plan"]), f["vence"],
                            f["sesiones"], round(f["horas"], 2),
                            round(f["excedente"], 2), round(importe)])

    print(f"  {'-' * 79}")
    print(f"  {'TOTAL A FACTURAR POR EXCEDENTES':<59}{total:>20,.0f}\n")

    if exportar:
        ruta = bd.exportar_csv(exportables, f"consumo_{mes}.csv",
                               ["Socio", "Plan", "Vence", "Sesiones", "Horas",
                                "Excedente", "A facturar"])
        print(f"  Exportado a {ruta}\n")


# ---------------- Ocupación por franja horaria ----------------
def ocupacion_por_hora(mes=None, exportar=False):
    """Cuenta cuántas sesiones estaban activas en cada hora del día."""
    mes = mes or _mes_actual()
    with bd.conectar() as con:
        registros = con.execute(
            "SELECT entrada, salida FROM registros "
            "WHERE strftime('%Y-%m', entrada) = ? AND salida IS NOT NULL", (mes,)).fetchall()

    conteo = {h: 0 for h in range(7, 24)}
    for r in registros:
        desde = datetime.strptime(r["entrada"], "%Y-%m-%d %H:%M:%S").hour
        hasta = datetime.strptime(r["salida"], "%Y-%m-%d %H:%M:%S").hour
        for h in range(desde, min(hasta + 1, 24)):
            if h in conteo:
                conteo[h] += 1

    maximo = max(conteo.values()) or 1
    print(f"\n{_linea()}")
    print(f"  OCUPACIÓN POR FRANJA HORARIA - {mes}")
    print(_linea())
    simbolo = "█"
    try:
        simbolo.encode(sys.stdout.encoding or "utf-8")
    except Exception:
        simbolo = "#"

    for h, cantidad in conteo.items():
        barra = simbolo * int(cantidad / maximo * 42)
        print(f"  {h:02d}:00  {barra:<42} {cantidad}")
    pico = max(conteo, key=conteo.get)
    print(f"\n  Hora pico: {pico:02d}:00 con {conteo[pico]} sesiones activas\n")

    if exportar:
        ruta = bd.exportar_csv([[f"{h:02d}:00", c] for h, c in conteo.items()],
                               f"ocupacion_{mes}.csv", ["Hora", "Sesiones activas"])
        print(f"  Exportado a {ruta}\n")


# ---------------- Historial de accesos ----------------
def historial_accesos(limite=30, exportar=False):
    with bd.conectar() as con:
        filas = con.execute(
            "SELECT nombre, entrada, salida, horas, excedente FROM registros "
            "ORDER BY entrada DESC LIMIT ?", (limite,)).fetchall()

    print(f"\n{_linea()}")
    print(f"  ÚLTIMOS {limite} ACCESOS")
    print(_linea())
    print(f"  {'SOCIO':<24}{'ENTRADA':<20}{'SALIDA':<20}{'HORAS':>7}")
    print(f"  {'-' * 71}")
    for f in filas:
        salida = f["salida"][11:16] if f["salida"] else "— adentro —"
        horas = f"{f['horas']:.2f}" if f["horas"] is not None else "—"
        print(f"  {f['nombre']:<24}{f['entrada'][:16]:<20}{salida:<20}{horas:>7}")
    print()

    if exportar:
        ruta = bd.exportar_csv([[f["nombre"], f["entrada"], f["salida"] or "",
                                 f["horas"] or "", f["excedente"] or 0] for f in filas],
                               "historial_accesos.csv",
                               ["Socio", "Entrada", "Salida", "Horas", "Excedente"])
        print(f"  Exportado a {ruta}\n")


# ---------------- Accesos rechazados ----------------
def accesos_rechazados(limite=30, exportar=False):
    filas = bd.listar_intentos(limite)
    print(f"\n{_linea()}")
    print(f"  ACCESOS RECHAZADOS E INTENTOS NO RECONOCIDOS")
    print(_linea())
    if not filas:
        print("  No hay intentos registrados.\n")
        return
    print(f"  {'MOMENTO':<22}{'PERSONA':<22}{'MOTIVO'}")
    print(f"  {'-' * 76}")
    for f in filas:
        print(f"  {f['momento'][:19]:<22}{(f['nombre'] or 'DESCONOCIDO'):<22}{f['motivo'][:34]}")
    print()

    if exportar:
        ruta = bd.exportar_csv([[f["momento"], f["nombre"] or "DESCONOCIDO", f["motivo"],
                                 f["foto"] or ""] for f in filas],
                               "accesos_rechazados.csv",
                               ["Momento", "Persona", "Motivo", "Foto"])
        print(f"  Exportado a {ruta}\n")


# ---------------- Padrón de socios ----------------
def padron_socios(exportar=False):
    socios = bd.listar_socios()
    hoy = datetime.now().date()
    print(f"\n{_linea()}")
    print(f"  PADRÓN DE SOCIOS ({len(socios)} activos)")
    print(_linea())
    print(f"  {'SOCIO':<24}{'PLAN':<24}{'VENCE':<12}{'ESTADO':<12}{'HORAS USADAS'}")
    print(f"  {'-' * 86}")
    exportables = []
    for s in socios:
        plan = config.PLANES.get(s["plan"], {})
        incluidas = plan.get("horas_incluidas")
        uso = f"{s['horas_usadas']:.1f}" + (f" / {incluidas}" if incluidas else " (libre)")
        dias = (datetime.strptime(s["vence"], "%Y-%m-%d").date() - hoy).days
        estado = "VENCIDO" if dias < 0 else (f"vence en {dias}d" if dias <= 7 else "vigente")
        print(f"  {s['nombre']:<24}{plan.get('nombre', s['plan'])[:23]:<24}"
              f"{s['vence']:<12}{estado:<12}{uso}")
        exportables.append([s["nombre"], plan.get("nombre", s["plan"]), s["vence"],
                            round(s["horas_usadas"], 2)])
    print()
    if exportar:
        ruta = bd.exportar_csv(exportables, "padron_socios.csv",
                               ["Socio", "Plan", "Vence", "Horas usadas"])
        print(f"  Exportado a {ruta}\n")


def mostrar_reglas():
    print()
    print(reglas.explicar_base_conocimiento())
    print()
