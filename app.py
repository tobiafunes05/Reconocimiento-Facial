"""
Servidor web y API REST para el Sistema de Coworking Facial.
Conecta la base de datos, el motor de reglas y el reconocimiento facial
con un panel de control interactivo y kiosco de acceso visual.
"""
import io
import os
import time
from datetime import datetime
import cv2
import numpy as np
from flask import Flask, render_template, jsonify, request, send_from_directory, Response, send_file

import config
import base_datos as bd
import reglas
import reconocimiento as rec
import control_acceso
import datos_demo

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["JSON_AS_ASCII"] = False

# Inicializar BD y caché de caras al arrancar
bd.conectar()
try:
    rec.cargar_base()
except Exception as e:
    print(f"[!] Error al cargar base de rostros: {e}")


# ==========================================================
# RUTAS DE PÁGINAS Y ARCHIVOS ESTÁTICOS
# ==========================================================
@app.route("/")
def index():
    return render_template("index.html", config=config)


@app.route("/fotos/socios/<path:filename>")
def foto_socio(filename):
    return send_from_directory(config.CARPETA_SOCIOS, filename)


@app.route("/fotos/intentos/<path:filename>")
def foto_intento(filename):
    return send_from_directory(config.CARPETA_INTENTOS, filename)


# ==========================================================
# API: ESTADO GENERAL Y DASHBOARD
# ==========================================================
@app.route("/api/estado")
def api_estado():
    """Resumen del estado general del coworking para el dashboard."""
    adentro = bd.personas_adentro()
    cant_adentro = len(adentro)
    socios = bd.listar_socios(solo_activos=True)
    
    # Calcular facturación y horas del mes
    mes_actual = datetime.now().strftime("%Y-%m")
    with bd.conectar() as con:
        totales = con.execute("""
            SELECT 
                COUNT(r.id) AS total_sesiones,
                IFNULL(SUM(r.horas), 0) AS total_horas,
                IFNULL(SUM(r.excedente), 0) AS total_excedente
            FROM registros r
            WHERE strftime('%Y-%m', r.entrada) = ? AND r.salida IS NOT NULL
        """, (mes_actual,)).fetchone()
        
        # Calcular importe total a facturar
        consumos = con.execute("""
            SELECT s.plan, IFNULL(SUM(r.excedente), 0) as excedente
            FROM socios s
            JOIN registros r ON r.socio_id = s.id
            WHERE strftime('%Y-%m', r.entrada) = ? AND r.salida IS NOT NULL
            GROUP BY s.id
        """, (mes_actual,)).fetchall()

    facturacion_total = 0
    for c in consumos:
        plan_cfg = config.PLANES.get(c["plan"], {})
        facturacion_total += c["excedente"] * plan_cfg.get("precio_hora_excedente", 0)

    # Sesiones activas hoy
    hoy = datetime.now().strftime("%Y-%m-%d")
    with bd.conectar() as con:
        sesiones_hoy = con.execute(
            "SELECT COUNT(*) FROM registros WHERE entrada LIKE ?", (f"{hoy}%",)
        ).fetchone()[0]

    return jsonify({
        "espacio": config.NOMBRE_ESPACIO,
        "aforo_maximo": config.AFORO_MAXIMO,
        "ocupacion_actual": cant_adentro,
        "porcentaje_ocupacion": round((cant_adentro / config.AFORO_MAXIMO) * 100, 1),
        "total_socios_activos": len(socios),
        "sesiones_hoy": sesiones_hoy,
        "horas_mes": round(totales["total_horas"], 1) if totales else 0,
        "facturacion_mes": round(facturacion_total, 2),
        "mes_actual": mes_actual,
        "fecha_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })


@app.route("/api/presentes")
def api_presentes():
    """Listado de personas que están adentro en este momento."""
    adentro = bd.personas_adentro()
    resultado = []
    ahora = datetime.now()
    for r in adentro:
        entrada = datetime.strptime(r["entrada"], "%Y-%m-%d %H:%M:%S")
        minutos = int((ahora - entrada).total_seconds() / 60)
        horas = round(minutos / 60, 2)
        
        # Foto del socio
        foto_url = f"/fotos/socios/{r['nombre']}.jpg" if os.path.exists(os.path.join(config.CARPETA_SOCIOS, f"{r['nombre']}.jpg")) else None
        
        resultado.append({
            "registro_id": r["id"],
            "socio_id": r["socio_id"],
            "nombre": r["nombre"],
            "plan": r["plan"],
            "plan_nombre": config.PLANES.get(r["plan"], {}).get("nombre", r["plan"]),
            "entrada": r["entrada"],
            "hora_entrada": entrada.strftime("%H:%M"),
            "tiempo_transcurrido": f"{minutos // 60}h {minutos % 60}m" if minutos >= 60 else f"{minutos} min",
            "horas": horas,
            "foto_url": foto_url
        })
    return jsonify(resultado)


# ==========================================================
# API: PADRÓN Y GESTIÓN DE SOCIOS
# ==========================================================
@app.route("/api/socios")
def api_socios():
    """Lista todos los socios con su estado, consumo y plan."""
    socios = bd.listar_socios(solo_activos=False)
    ahora = datetime.now()
    resultado = []
    
    for s in socios:
        plan_cfg = config.PLANES.get(s["plan"], config.PLANES["invitado"])
        vence = datetime.strptime(s["vence"], "%Y-%m-%d")
        dias_restantes = (vence.date() - ahora.date()).days
        
        # Estado
        if not s["activo"]:
            estado_codigo = "inactivo"
            estado_texto = "Inactivo"
        elif dias_restantes < 0:
            estado_codigo = "vencido"
            estado_texto = "Vencido"
        elif dias_restantes <= config.DIAS_AVISO_VENCIMIENTO:
            estado_codigo = "por_vencer"
            estado_texto = f"Vence en {dias_restantes}d"
        else:
            estado_codigo = "vigente"
            estado_texto = "Vigente"

        incluidas = plan_cfg.get("horas_incluidas")
        horas_usadas = round(s["horas_usadas"] or 0, 1)
        porcentaje_horas = 0
        if incluidas:
            porcentaje_horas = min(round((horas_usadas / incluidas) * 100), 100)

        foto_existe = os.path.exists(os.path.join(config.CARPETA_SOCIOS, f"{s['nombre']}.jpg"))
        foto_url = f"/fotos/socios/{s['nombre']}.jpg" if foto_existe else None

        resultado.append({
            "id": s["id"],
            "nombre": s["nombre"],
            "plan": s["plan"],
            "plan_nombre": plan_cfg.get("nombre", s["plan"]),
            "vence": s["vence"],
            "dias_restantes": dias_restantes,
            "estado_codigo": estado_codigo,
            "estado_texto": estado_texto,
            "horas_usadas": horas_usadas,
            "horas_incluidas": incluidas,
            "porcentaje_horas": porcentaje_horas,
            "activo": bool(s["activo"]),
            "alta": s["alta"],
            "foto_url": foto_url
        })
    return jsonify(resultado)


@app.route("/api/socios/alta", methods=["POST"])
def api_alta_socio():
    """Registra un nuevo socio y guarda su fotografía."""
    nombre = request.form.get("nombre", "").strip()
    plan = request.form.get("plan", "").strip()
    dias = int(request.form.get("dias", 30))
    foto_archivo = request.files.get("foto")
    foto_b64 = request.form.get("foto_b64")

    if not nombre or not plan:
        return jsonify({"error": "Nombre y plan son requeridos"}), 400

    if plan not in config.PLANES:
        return jsonify({"error": f"Plan inválido. Opciones: {list(config.PLANES.keys())}"}), 400

    if bd.obtener_socio(nombre):
        return jsonify({"error": f"Ya existe un socio con el nombre '{nombre}'"}), 400

    os.makedirs(config.CARPETA_SOCIOS, exist_ok=True)
    ruta_foto = os.path.join(config.CARPETA_SOCIOS, f"{nombre}.jpg")

    # Guardar foto si viene en el request
    if foto_archivo and foto_archivo.filename:
        foto_archivo.save(ruta_foto)
    elif foto_b64 and "," in foto_b64:
        import base64
        datos_b64 = foto_b64.split(",")[1]
        with open(ruta_foto, "wb") as f:
            f.write(base64.b64decode(datos_b64))

    # Dar de alta en base de datos
    ruta_guardada = ruta_foto if os.path.exists(ruta_foto) else None
    socio_id = bd.alta_socio(nombre, plan, dias, ruta_guardada)

    # Actualizar caché de codificaciones faciales
    try:
        rec.cargar_base(forzar=True)
    except Exception as e:
        print(f"[!] Aviso al recodificar: {e}")

    return jsonify({
        "mensaje": f"Socio '{nombre}' registrado exitosamente",
        "socio_id": socio_id,
        "plan": plan
    })


@app.route("/api/socios/<int:socio_id>/renovar", methods=["POST"])
def api_renovar_socio(socio_id):
    """Renueva el plan de un socio por 30 días y reinicia horas."""
    socio = None
    with bd.conectar() as con:
        socio = con.execute("SELECT * FROM socios WHERE id = ?", (socio_id,)).fetchone()
    if not socio:
        return jsonify({"error": "Socio no encontrado"}), 404

    datos = request.get_json(silent=True) or {}
    nuevo_plan = datos.get("plan", socio["plan"])
    dias = int(datos.get("dias", 30))

    bd.renovar_plan(socio["nombre"], nuevo_plan, dias)
    return jsonify({"mensaje": f"Plan de '{socio['nombre']}' renovado con éxito"})


@app.route("/api/socios/<int:socio_id>/baja", methods=["POST"])
def api_baja_socio(socio_id):
    """Elimina definitivamente a un socio, sus registros y su foto."""
    socio = None
    with bd.conectar() as con:
        socio = con.execute("SELECT * FROM socios WHERE id = ?", (socio_id,)).fetchone()
    if not socio:
        return jsonify({"error": "Socio no encontrado"}), 404

    nombre = socio["nombre"]
    bd.baja_socio(nombre, borrar_foto=True)

    # Actualizar caché de reconocimiento facial para remover su vector
    try:
        rec.cargar_base(forzar=True)
    except Exception as e:
        print(f"[!] Error al actualizar rostros tras baja: {e}")

    return jsonify({"mensaje": f"Socio '{nombre}' eliminado definitivamente del sistema"})


# ==========================================================
# API: CONTROL DE ACCESO, SIMULACIÓN Y CHECKOUT
# ==========================================================
@app.route("/api/acceso/simular", methods=["POST"])
def api_simular_acceso():
    """
    Simula la detección facial y evalúa el motor de reglas.
    Puede recibir el nombre del socio o una foto para reconocimiento.
    """
    datos = request.get_json(silent=True) or {}
    nombre = datos.get("nombre")

    # Si se sube una imagen para simular escaneo facial
    if "foto" in request.files:
        archivo = request.files["foto"]
        import cv2
        import numpy as np
        img_bytes = archivo.read()
        nparr = np.frombuffer(img_bytes, np.uint8)
        fotograma = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        caras = rec.buscar_rostros(fotograma)
        if not caras:
            bd.registrar_intento(None, "Cara no reconocida")
            return jsonify({
                "decision": reglas.RECHAZADO,
                "nombre": "Desconocido",
                "tipo_movimiento": "DENEGADO",
                "etiqueta": "ACCESO DENEGADO",
                "motivo": "No se detectó ningún rostro reconocible",
                "foto_intento": None
            })
        
        ubicacion, cod = caras[0]
        nombres_db, cods_db = rec.cargar_base()
        nombre_id, dist = rec.identificar(cod, nombres_db, cods_db)
        if not nombre_id:
            bd.registrar_intento(None, "Persona desconocida (no registrada)")
            return jsonify({
                "decision": reglas.RECHAZADO,
                "nombre": "Desconocido",
                "tipo_movimiento": "DENEGADO",
                "etiqueta": "DESCONOCIDO",
                "motivo": "Rostro no registrado en el padrón de socios",
                "foto_intento": None
            })
        nombre = nombre_id

    if not nombre:
        return jsonify({"error": "Debe especificar un nombre o una fotografía"}), 400

    socio = bd.obtener_socio(nombre)
    if not socio:
        return jsonify({
            "decision": reglas.RECHAZADO,
            "nombre": nombre,
            "tipo_movimiento": "DENEGADO",
            "etiqueta": f"RECHAZADO: {nombre}",
            "motivo": "No figura en el sistema"
        })

    socio = bd.reiniciar_periodo_si_cambio_mes(socio)
    abierto = bd.registro_abierto(socio["id"])

    # SALIDA: Si la persona ya está adentro
    if abierto:
        entrada = datetime.strptime(abierto["entrada"], "%Y-%m-%d %H:%M:%S")
        horas = round((datetime.now() - entrada).total_seconds() / 3600, 2)
        dentro, excedente, importe = reglas.calcular_consumo(socio, horas)
        bd.registrar_salida(abierto["id"], horas, excedente)
        bd.sumar_horas_usadas(socio["id"], horas)

        detalle = f"Sesión de {horas:.2f} h"
        if excedente > 0:
            detalle += f" | {excedente:.2f} h excedente (${importe:,.0f})"

        return jsonify({
            "decision": reglas.HABILITADO,
            "tipo_movimiento": "SALIDA",
            "nombre": nombre,
            "etiqueta": f"CHAU {nombre}",
            "detalle": detalle,
            "horas_sesion": horas,
            "excedente": excedente,
            "importe": importe,
            "socio_id": socio["id"]
        })

    # ENTRADA: Si la persona está afuera
    analisis = reglas.evaluar_acceso(socio, bd.cantidad_adentro(), bd.reserva_de_hoy(socio["id"]))

    if analisis["decision"] == reglas.RECHAZADO:
        bd.registrar_intento(nombre, analisis["motivo"])
        return jsonify({
            "decision": reglas.RECHAZADO,
            "tipo_movimiento": "DENEGADO",
            "nombre": nombre,
            "etiqueta": f"RECHAZADO {nombre}",
            "motivo": analisis["motivo"],
            "regla_violada": analisis.get("regla"),
            "socio_id": socio["id"]
        })

    bd.registrar_entrada(socio["id"], nombre)
    detalle = " | ".join(analisis["avisos"]) if analisis["avisos"] else config.PLANES[socio["plan"]]["nombre"]

    return jsonify({
        "decision": analisis["decision"],
        "tipo_movimiento": "ENTRADA",
        "nombre": nombre,
        "etiqueta": f"HOLA {nombre}",
        "detalle": detalle,
        "avisos": analisis["avisos"],
        "socio_id": socio["id"]
    })


@app.route("/api/acceso/checkout_manual", methods=["POST"])
def api_checkout_manual():
    """Fuerza la salida de un socio que figura adentro."""
    datos = request.get_json(silent=True) or {}
    registro_id = datos.get("registro_id")
    if not registro_id:
        return jsonify({"error": "Se requiere registro_id"}), 400

    with bd.conectar() as con:
        r = con.execute("SELECT * FROM registros WHERE id = ?", (registro_id,)).fetchone()
        if not r or r["salida"] is not None:
            return jsonify({"error": "Registro no encontrado o ya cerrado"}), 404
        
        socio = con.execute("SELECT * FROM socios WHERE id = ?", (r["socio_id"],)).fetchone()
        entrada = datetime.strptime(r["entrada"], "%Y-%m-%d %H:%M:%S")
        horas = round((datetime.now() - entrada).total_seconds() / 3600, 2)
        dentro, excedente, importe = reglas.calcular_consumo(socio, horas)
        
        bd.registrar_salida(registro_id, horas, excedente)
        bd.sumar_horas_usadas(socio["id"], horas)

    return jsonify({
        "mensaje": f"Salida registrada para {r['nombre']}",
        "horas": horas,
        "excedente": excedente
    })


# ==========================================================
# API: REPORTES, ANALÍTICA Y OCUPACIÓN
# ==========================================================
@app.route("/api/consumo")
def api_consumo():
    """Reporte de consumo y facturación por socio."""
    mes = request.args.get("mes", datetime.now().strftime("%Y-%m"))
    with bd.conectar() as con:
        filas = con.execute("""
            SELECT s.id, s.nombre, s.plan, s.vence,
                   COUNT(r.id)                AS sesiones,
                   IFNULL(SUM(r.horas), 0)    AS horas,
                   IFNULL(SUM(r.excedente),0) AS excedente
            FROM socios s
            LEFT JOIN registros r ON r.socio_id = s.id
                 AND strftime('%Y-%m', r.entrada) = ? AND r.salida IS NOT NULL
            WHERE s.activo = 1
            GROUP BY s.id ORDER BY horas DESC
        """, (mes,)).fetchall()

    resultado = []
    total_facturar = 0
    total_horas = 0
    total_sesiones = 0

    for f in filas:
        plan_cfg = config.PLANES.get(f["plan"], {})
        precio_excedente = plan_cfg.get("precio_hora_excedente", 0)
        importe = round(f["excedente"] * precio_excedente)
        total_facturar += importe
        total_horas += f["horas"]
        total_sesiones += f["sesiones"]

        resultado.append({
            "socio_id": f["id"],
            "nombre": f["nombre"],
            "plan": f["plan"],
            "plan_nombre": plan_cfg.get("nombre", f["plan"]),
            "horas_incluidas": plan_cfg.get("horas_incluidas"),
            "vence": f["vence"],
            "sesiones": f["sesiones"],
            "horas": round(f["horas"], 1),
            "excedente": round(f["excedente"], 1),
            "precio_hora_excedente": precio_excedente,
            "importe": importe
        })

    return jsonify({
        "mes": mes,
        "socios": resultado,
        "total_facturar": total_facturar,
        "total_horas": round(total_horas, 1),
        "total_sesiones": total_sesiones
    })


@app.route("/api/ocupacion")
def api_ocupacion():
    """Datos de ocupación por hora del día para renderizar gráficos."""
    mes = request.args.get("mes", datetime.now().strftime("%Y-%m"))
    with bd.conectar() as con:
        registros = con.execute("""
            SELECT entrada, salida FROM registros
            WHERE strftime('%Y-%m', entrada) = ? AND salida IS NOT NULL
        """, (mes,)).fetchall()

    conteo = {h: 0 for h in range(7, 24)}
    for r in registros:
        desde = datetime.strptime(r["entrada"], "%Y-%m-%d %H:%M:%S").hour
        hasta = datetime.strptime(r["salida"], "%Y-%m-%d %H:%M:%S").hour
        for h in range(max(desde, 7), min(hasta + 1, 24)):
            conteo[h] += 1

    etiquetas = [f"{h:02d}:00" for h in range(7, 24)]
    valores = [conteo[h] for h in range(7, 24)]

    # Hora pico
    hora_pico = max(conteo, key=conteo.get)
    max_concurrencia = conteo[hora_pico]

    return jsonify({
        "mes": mes,
        "etiquetas": etiquetas,
        "valores": valores,
        "hora_pico": f"{hora_pico:02d}:00 hs",
        "max_concurrencia": max_concurrencia,
        "total_sesiones_analizadas": len(registros)
    })


@app.route("/api/historial")
def api_historial():
    """Últimos accesos registrados en el coworking."""
    limite = int(request.args.get("limite", 30))
    with bd.conectar() as con:
        registros = con.execute("""
            SELECT r.*, s.plan
            FROM registros r
            JOIN socios s ON s.id = r.socio_id
            ORDER BY r.entrada DESC LIMIT ?
        """, (limite,)).fetchall()

    resultado = []
    for r in registros:
        resultado.append({
            "id": r["id"],
            "socio_id": r["socio_id"],
            "nombre": r["nombre"],
            "plan": r["plan"],
            "plan_nombre": config.PLANES.get(r["plan"], {}).get("nombre", r["plan"]),
            "entrada": r["entrada"],
            "salida": r["salida"] or "Adentro ahora",
            "horas": round(r["horas"], 2) if r["horas"] is not None else None,
            "excedente": round(r["excedente"], 2) if r["excedente"] is not None else 0
        })
    return jsonify(resultado)


@app.route("/api/intentos")
def api_intentos():
    """Intentos denegados o rostros desconocidos."""
    limite = int(request.args.get("limite", 25))
    intentos = bd.listar_intentos(limite=limite)
    resultado = []
    for i in intentos:
        foto_rel = os.path.basename(i["foto"]) if i["foto"] else None
        resultado.append({
            "id": i["id"],
            "momento": i["momento"],
            "nombre": i["nombre"] or "Persona Desconocida",
            "motivo": i["motivo"],
            "foto_url": f"/fotos/intentos/{foto_rel}" if foto_rel else None
        })
    return jsonify(resultado)


# ==========================================================
# API: MOTOR DE REGLAS Y SANDBOX DE INGENIERÍA DEL CONOCIMIENTO
# ==========================================================
@app.route("/api/reglas")
def api_reglas():
    """Listado de reglas de la base de conocimiento con metadatos."""
    lista = []
    for r in reglas.BASE_CONOCIMIENTO:
        lista.append({
            "codigo": r["codigo"],
            "descripcion": r["descripcion"],
            "decision": r["decision"]
        })
    return jsonify(lista)


@app.route("/api/reglas/evaluar", methods=["POST"])
def api_evaluar_reglas():
    """
    Sandbox interactivo: Evalúa qué reglas se disparan para un socio
    según parámetros hipotéticos (hora, aforo, horas consumidas).
    Ideal para demostración y evaluación académica del TP.
    """
    datos = request.get_json(silent=True) or {}
    nombre = datos.get("nombre")
    socio = bd.obtener_socio(nombre) if nombre else None
    
    if not socio:
        return jsonify({"error": "Socio no encontrado"}), 404

    # Parámetros hipotéticos
    hora_simulada = int(datos.get("hora", datetime.now().hour))
    aforo_simulado = int(datos.get("adentro", bd.cantidad_adentro()))
    horas_usadas_simuladas = float(datos.get("horas_usadas", socio["horas_usadas"] or 0))

    # Crear socio y contexto simulado
    socio_simulado = dict(socio)
    socio_simulado["horas_usadas"] = horas_usadas_simuladas
    if "activo" in datos:
        socio_simulado["activo"] = 1 if datos["activo"] else 0
    if "vence" in datos and datos["vence"]:
        socio_simulado["vence"] = datos["vence"]

    ahora_simulado = datetime.now().replace(hour=hora_simulada, minute=0, second=0)
    ctx = {
        "ahora": ahora_simulado,
        "adentro": aforo_simulado,
        "reserva": None,
    }

    evaluaciones = []
    decision_final = reglas.HABILITADO
    motivo_final = None

    for r in reglas.BASE_CONOCIMIENTO:
        se_cumple = r["condicion"](socio_simulado, ctx)
        mensaje = r["mensaje"](socio_simulado, ctx) if se_cumple else None
        
        evaluaciones.append({
            "codigo": r["codigo"],
            "descripcion": r["descripcion"],
            "decision": r["decision"],
            "se_cumple": bool(se_cumple),
            "mensaje": mensaje
        })

        if se_cumple and r["decision"] == reglas.RECHAZADO and decision_final != reglas.RECHAZADO:
            decision_final = reglas.RECHAZADO
            motivo_final = mensaje
        elif se_cumple and r["decision"] == reglas.ADVERTENCIA and decision_final == reglas.HABILITADO:
            decision_final = reglas.ADVERTENCIA

    return jsonify({
        "socio": socio_simulado["nombre"],
        "plan": socio_simulado["plan"],
        "decision_final": decision_final,
        "motivo_final": motivo_final,
        "evaluaciones": evaluaciones,
        "parametros": {
            "hora": hora_simulada,
            "aforo": aforo_simulado,
            "horas_usadas": horas_usadas_simuladas
        }
    })


# ==========================================================
# API: RECARGAR DATOS DEMO Y EXPORTACIÓN CSV
# ==========================================================
@app.route("/api/demo/recargar", methods=["POST"])
def api_recargar_demo():
    """Vuelve a generar los datos de prueba y accesos del mes."""
    try:
        datos_demo.cargar(con_historial=True)
        rec.cargar_base(forzar=True)
        return jsonify({"mensaje": "Datos de prueba recargados correctamente"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/exportar/<tipo>")
def api_exportar_csv(tipo):
    """Genera y descarga directamente un archivo CSV del reporte solicitado."""
    mes = request.args.get("mes", datetime.now().strftime("%Y-%m"))
    
    if tipo == "consumo":
        with bd.conectar() as con:
            filas = con.execute("""
                SELECT s.nombre, s.plan, s.vence,
                       COUNT(r.id) AS sesiones,
                       IFNULL(SUM(r.horas), 0) AS horas,
                       IFNULL(SUM(r.excedente),0) AS excedente
                FROM socios s
                LEFT JOIN registros r ON r.socio_id = s.id
                     AND strftime('%Y-%m', r.entrada) = ? AND r.salida IS NOT NULL
                WHERE s.activo = 1
                GROUP BY s.id ORDER BY horas DESC
            """, (mes,)).fetchall()
            
        exportables = []
        for f in filas:
            plan = config.PLANES.get(f["plan"], {})
            importe = round(f["excedente"] * plan.get("precio_hora_excedente", 0))
            exportables.append([
                f["nombre"], plan.get("nombre", f["plan"]), f["vence"],
                f["sesiones"], round(f["horas"], 2), round(f["excedente"], 2), importe
            ])
            
        ruta = bd.exportar_csv(exportables, f"consumo_{mes}.csv",
                               ["Socio", "Plan", "Vence", "Sesiones", "Horas", "Excedente", "A facturar"])
        return send_file(ruta, as_attachment=True, download_name=f"consumo_{mes}.csv")

    elif tipo == "padron":
        socios = bd.listar_socios(solo_activos=False)
        filas = []
        for s in socios:
            filas.append([s["nombre"], config.PLANES.get(s["plan"], {}).get("nombre", s["plan"]),
                          s["vence"], round(s["horas_usadas"] or 0, 1),
                          "Activo" if s["activo"] else "Inactivo", s["alta"]])
        ruta = bd.exportar_csv(filas, "padron_socios.csv",
                               ["Nombre", "Plan", "Vencimiento", "Horas Usadas", "Estado", "Fecha Alta"])
        return send_file(ruta, as_attachment=True, download_name="padron_socios.csv")

    elif tipo == "historial":
        with bd.conectar() as con:
            regs = con.execute("SELECT * FROM registros ORDER BY entrada DESC LIMIT 200").fetchall()
        filas = [[r["nombre"], r["entrada"], r["salida"] or "EN CURSO", r["horas"] or 0, r["excedente"] or 0] for r in regs]
        ruta = bd.exportar_csv(filas, "historial_accesos.csv", ["Nombre", "Entrada", "Salida", "Horas", "Excedente"])
        return send_file(ruta, as_attachment=True, download_name="historial_accesos.csv")

    return jsonify({"error": "Tipo de reporte desconocido"}), 400


# ==========================================================
# STREAMING DE VIDEO EN VIVO
# ==========================================================
def _generar_frames():
    """Genera stream MJPEG de video con recuadros faciales."""
    import cv2
    cam = cv2.VideoCapture(config.INDICE_CAMARA)
    if not cam.isOpened():
        # Generar imagen sintética informativa
        blank = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(blank, "Camara no disponible", (160, 240),
                    cv2.FONT_HERSHEY_DUPLEX, 0.8, (255, 255, 255), 1)
        _, buffer = cv2.imencode(".jpg", blank)
        frame_bytes = buffer.tobytes()
        while True:
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
            time.sleep(1)

    nombres_db, cods_db = rec.cargar_base()
    contador = 0
    caras_actuales = []

    while True:
        exito, frame = cam.read()
        if not exito:
            break

        contador += 1
        # Procesar 1 de cada N fotogramas para rendimiento fluido
        if contador % config.SALTEAR_FOTOGRAMAS == 0:
            caras = rec.buscar_rostros(frame)
            caras_actuales = []
            for ubicacion, cod in caras:
                nombre, dist = rec.identificar(cod, nombres_db, cods_db)
                if nombre:
                    socio = bd.obtener_socio(nombre)
                    if socio:
                        abierto = bd.registro_abierto(socio["id"])
                        estado = "ADENTRO (Check-out)" if abierto else "AFUERA (Ingreso)"
                        color = config.COLOR_HABILITADO
                    else:
                        estado = "No registrado"
                        color = config.COLOR_RECHAZADO
                    caras_actuales.append((ubicacion, nombre, color, estado))
                else:
                    caras_actuales.append((ubicacion, "DESCONOCIDO", config.COLOR_DESCONOCIDO, "No reconocido"))

        # Dibujar recuadros
        for ubicacion, etiqueta, color, sub in caras_actuales:
            rec.dibujar_rostro(frame, ubicacion, etiqueta, color, sub)

        # Franja superior
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 36), (20, 20, 24), cv2.FILLED)
        cv2.putText(frame, f"{config.NOMBRE_ESPACIO} | Aforo: {bd.cantidad_adentro()}/{config.AFORO_MAXIMO}",
                    (12, 24), cv2.FONT_HERSHEY_DUPLEX, 0.55, (255, 255, 255), 1)

        ret, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        frame_bytes = buffer.tobytes()
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")

    cam.release()


@app.route("/api/video_feed")
def video_feed():
    """Ruta para transmitir video MJPEG en tiempo real a la interfaz web."""
    return Response(_generar_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


if __name__ == "__main__":
    print(f"\n========================================================")
    print(f"  {config.NOMBRE_ESPACIO} - SERVIDOR WEB INICIADO")
    print(f"  Panel y Kiosco disponible en: http://127.0.0.1:5000")
    print(f"========================================================\n")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
