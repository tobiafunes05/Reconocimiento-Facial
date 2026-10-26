"""
Motor de reglas de acceso (base de conocimiento del sistema).

El reconocimiento facial responde "quién es". Este módulo responde "puede entrar".

Cada regla tiene:
    codigo      identificador de la regla
    descripcion qué verifica, en palabras
    condicion   función que devuelve True cuando la regla se incumple
    decision    RECHAZADO (no entra) o ADVERTENCIA (entra, pero se le avisa)
    mensaje     texto que se muestra en pantalla

El motor evalúa las reglas en orden. La primera regla de rechazo que se cumple
corta la evaluación; las advertencias se acumulan y no impiden el ingreso.
"""
from datetime import datetime

import config

HABILITADO = "HABILITADO"
ADVERTENCIA = "ADVERTENCIA"
RECHAZADO = "RECHAZADO"


def _plan_de(socio):
    return config.PLANES.get(socio["plan"], config.PLANES["invitado"])


def _dias_para_vencer(socio, ahora):
    vence = datetime.strptime(socio["vence"], "%Y-%m-%d").date()
    return (vence - ahora.date()).days


def _horas_restantes(socio):
    """Horas que le quedan en la bolsa. None si el plan es ilimitado."""
    incluidas = _plan_de(socio)["horas_incluidas"]
    if incluidas is None:
        return None
    return incluidas - (socio["horas_usadas"] or 0)


# ---------------- Reglas ----------------
# Orden importante: primero las que rechazan, después las que solo avisan.
BASE_CONOCIMIENTO = [
    {
        "codigo": "R1_SOCIO_INACTIVO",
        "descripcion": "El socio debe estar activo en el sistema",
        "decision": RECHAZADO,
        "condicion": lambda s, ctx: not s["activo"],
        "mensaje": lambda s, ctx: "Membresía dada de baja. Pasá por recepción",
    },
    {
        "codigo": "R2_PLAN_VENCIDO",
        "descripcion": "El plan contratado no debe estar vencido",
        "decision": RECHAZADO,
        "condicion": lambda s, ctx: _dias_para_vencer(s, ctx["ahora"]) < 0,
        "mensaje": lambda s, ctx: f"Plan vencido el {s['vence']}. Renovalo en recepción",
    },
    {
        "codigo": "R3_FUERA_DE_HORARIO",
        "descripcion": "La hora de ingreso debe estar dentro de la franja del plan",
        "decision": RECHAZADO,
        "condicion": lambda s, ctx: not (_plan_de(s)["hora_desde"] <= ctx["ahora"].hour < _plan_de(s)["hora_hasta"]),
        "mensaje": lambda s, ctx: (f"{_plan_de(s)['nombre']}: acceso de "
                                   f"{_plan_de(s)['hora_desde']} a {_plan_de(s)['hora_hasta']} hs"),
    },
    {
        "codigo": "R4_BOLSA_AGOTADA",
        "descripcion": "El socio no debe haber consumido toda su bolsa de horas",
        "decision": RECHAZADO,
        "condicion": lambda s, ctx: (_horas_restantes(s) is not None and _horas_restantes(s) <= 0
                                     and _plan_de(s)["precio_hora_excedente"] == 0),
        "mensaje": lambda s, ctx: "Agotaste las horas de tu plan. Ampliá el plan en recepción",
    },
    {
        "codigo": "R5_AFORO_COMPLETO",
        "descripcion": "No se puede superar el aforo máximo del espacio",
        "decision": RECHAZADO,
        "condicion": lambda s, ctx: ctx["adentro"] >= config.AFORO_MAXIMO,
        "mensaje": lambda s, ctx: f"Espacio completo ({ctx['adentro']}/{config.AFORO_MAXIMO}). Esperá un lugar",
    },
    {
        "codigo": "R6_BOLSA_EN_EXCEDENTE",
        "descripcion": "Avisar cuando las horas consumidas ya se facturan como excedente",
        "decision": ADVERTENCIA,
        "condicion": lambda s, ctx: _horas_restantes(s) is not None and _horas_restantes(s) <= 0,
        "mensaje": lambda s, ctx: (f"Sin horas en el plan: desde ahora se facturan a "
                                   f"${_plan_de(s)['precio_hora_excedente']} la hora"),
    },
    {
        "codigo": "R7_BOLSA_BAJA",
        "descripcion": "Avisar cuando quedan pocas horas en la bolsa contratada",
        "decision": ADVERTENCIA,
        "condicion": lambda s, ctx: (_horas_restantes(s) is not None
                                     and 0 < _horas_restantes(s) <= config.HORAS_AVISO_BOLSA),
        "mensaje": lambda s, ctx: f"Te quedan {_horas_restantes(s):.1f} horas este mes",
    },
    {
        "codigo": "R8_POR_VENCER",
        "descripcion": "Avisar cuando el plan está por vencer",
        "decision": ADVERTENCIA,
        "condicion": lambda s, ctx: 0 <= _dias_para_vencer(s, ctx["ahora"]) <= config.DIAS_AVISO_VENCIMIENTO,
        "mensaje": lambda s, ctx: f"Tu plan vence en {_dias_para_vencer(s, ctx['ahora'])} días",
    },
    {
        "codigo": "R9_RESERVA_DE_HOY",
        "descripcion": "Recordar la reserva de sala del día",
        "decision": ADVERTENCIA,
        "condicion": lambda s, ctx: ctx.get("reserva") is not None,
        "mensaje": lambda s, ctx: (f"Tenés {ctx['reserva']['sala']} reservada de "
                                   f"{ctx['reserva']['hora_desde']} a {ctx['reserva']['hora_hasta']}"),
    },
]


def evaluar_acceso(socio, cantidad_adentro, reserva=None, ahora=None):
    """
    Aplica la base de conocimiento y devuelve el resultado del análisis:

    {
        "decision": HABILITADO | ADVERTENCIA | RECHAZADO,
        "motivo":   texto principal que se muestra en pantalla,
        "avisos":   lista de advertencias,
        "reglas":   códigos de las reglas que se activaron (para la traza)
    }
    """
    ahora = ahora or datetime.now()
    contexto = {"ahora": ahora, "adentro": cantidad_adentro, "reserva": reserva}
    avisos, activadas = [], []

    for regla in BASE_CONOCIMIENTO:
        try:
            if not regla["condicion"](socio, contexto):
                continue
        except Exception:
            continue                      # una regla que falla no debe frenar el sistema
        activadas.append(regla["codigo"])
        mensaje = regla["mensaje"](socio, contexto)
        if regla["decision"] == RECHAZADO:
            return {"decision": RECHAZADO, "motivo": mensaje, "avisos": avisos, "reglas": activadas}
        avisos.append(mensaje)

    if avisos:
        return {"decision": ADVERTENCIA, "motivo": avisos[0], "avisos": avisos, "reglas": activadas}
    return {"decision": HABILITADO, "motivo": "Acceso habilitado", "avisos": [], "reglas": activadas}


def calcular_consumo(socio, horas):
    """
    Reparte las horas de una sesión entre las incluidas en el plan y el excedente a facturar.
    Devuelve (horas_dentro_del_plan, horas_excedente, importe_excedente).
    """
    plan = _plan_de(socio)
    incluidas = plan["horas_incluidas"]
    if incluidas is None:
        return horas, 0.0, 0.0
    disponibles = max(incluidas - (socio["horas_usadas"] or 0), 0)
    dentro = min(horas, disponibles)
    excedente = max(horas - disponibles, 0)
    return dentro, excedente, excedente * plan["precio_hora_excedente"]


def explicar_base_conocimiento():
    """Devuelve la base de conocimiento en texto, para mostrarla en la defensa del trabajo."""
    lineas = ["BASE DE CONOCIMIENTO - REGLAS DE ACCESO", "=" * 60]
    for regla in BASE_CONOCIMIENTO:
        lineas.append(f"[{regla['decision']:11}] {regla['codigo']}")
        lineas.append(f"              {regla['descripcion']}")
    return "\n".join(lineas)
