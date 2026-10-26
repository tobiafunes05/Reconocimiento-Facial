# Sistema de control de acceso y consumo de horas por reconocimiento facial

**Ingeniería del Conocimiento — 2° Proyecto: Sistema de Asistencias**
Universidad del Aconcagua — Licenciatura en Informática y Desarrollo de Software

Sistema para un espacio de coworking. El reconocimiento facial no solo registra
la asistencia: **valida el plan contratado y habilita o rechaza el ingreso**, mide
las horas consumidas y calcula lo que hay que facturar.

---

## 1. Instalación

> **Hagan esto varios días antes de la entrega.** Es la parte que más se traba.

```bash
pip install -r requirements.txt
```

### Si falla `dlib` (Windows)

`face_recognition` usa `dlib`, que se compila al instalarse:

1. Instalar **CMake** desde https://cmake.org/download/ (marcar *Add CMake to the PATH*).
2. Instalar **Visual Studio Build Tools** con la carga "Desarrollo para el escritorio con C++".
3. Reiniciar la terminal y volver a intentar.

Si igual no compila, hay ruedas precompiladas que evitan todo el paso anterior:

```bash
pip install dlib-bin
pip install face_recognition
```

### Si falla `face-recognition-models`

Con versiones nuevas de Python o de `setuptools` aparece
`AttributeError: install_layout`. Es un problema del instalador de ese paquete,
no del código. Se soluciona instalándolo desde el repositorio:

```bash
pip install git+https://github.com/ageitgey/face_recognition_models
pip install face_recognition --no-deps
```

### Comprobar que quedó bien

```bash
python -c "import face_recognition, cv2; print('Todo OK')"
```

---

## 2. Primeros pasos

```bash
python main.py demo        # carga 7 socios de prueba y un mes de historial
python main.py web         # Inicia la INTERFAZ WEB PROFESIONAL en http://127.0.0.1:5000
python main.py padron      # ver el padrón por consola
python main.py consumo     # ver el consumo y la facturación
python main.py acceso      # abrir la cámara y empezar a controlar
```

Para usarlo con gente real, borrar la carpeta `datos/` y las fotos de `Socios/`,
y dar de alta a cada persona con `python main.py alta` o desde la nueva **Interfaz Web**.

---

## 3. Comandos

| Comando | Qué hace |
|---|---|
| `python main.py web` | **Interfaz visual profesional (Dashboard, Kiosco Facial, Padrón, Gráficos y Sandbox de IA)** |
| `python app.py` | Ejecuta directamente el servidor de la aplicación web en el puerto 5000 |
| `python main.py` | Menú interactivo de consola con todas las opciones |
| `python main.py acceso` | Control de acceso en tiempo real con la cámara (Q para salir) |
| `python main.py acceso 1` | Igual, pero con la cámara número 1 (si hay varias) |
| `python main.py alta` | Da de alta un socio tomándole la foto con la cámara |
| `python main.py importar` | Da de alta las fotos que ya estén en `Socios/` |
| `python main.py simular FOTO` | Procesa una foto como si viniera de la cámara (para probar sin webcam) |
| `python main.py panel` | Quiénes están adentro en este momento |
| `python main.py consumo` | Horas y facturación del mes |
| `python main.py ocupacion` | Gráfico de ocupación por franja horaria |
| `python main.py historial` | Últimos accesos registrados |
| `python main.py rechazados` | Accesos denegados y caras desconocidas |
| `python main.py padron` | Padrón de socios con planes y vencimientos |
| `python main.py reglas` | Muestra la base de conocimiento |
| `python comparar_caras.py A.jpg B.jpg` | Compara dos fotos (primer script del enunciado) |

A cualquier reporte se le puede agregar `csv` al final para exportarlo:
`python main.py consumo csv`

---

## 4. Estructura del proyecto

| Archivo | Responsabilidad | Librerías |
|---|---|---|
| `main.py` | Menú y punto de entrada | — |
| `config.py` | Parámetros: planes, aforo, tolerancia, rutas | `os` |
| `comparar_caras.py` | Comparación de dos rostros (script 1 del enunciado) | `face_recognition`, `cv2` |
| `reconocimiento.py` | Carga, codificación y comparación de rostros | `face_recognition`, `cv2`, `numpy` |
| `base_datos.py` | SQLite: socios, registros, reservas e intentos | `sqlite3`, `csv`, `datetime` |
| `reglas.py` | **Motor de reglas de acceso (base de conocimiento)** | `datetime` |
| `control_acceso.py` | Control en tiempo real (script 2 del enunciado) | `cv2`, `datetime` |
| `alta_socios.py` | Alta de socios con captura de foto | `cv2`, `os` |
| `reportes.py` | Consumo, ocupación, historial y exportación | `datetime` |
| `datos_demo.py` | Datos de prueba | `random`, `datetime` |

Y las carpetas: `Socios/` (fotos), `datos/` (base de datos), `reportes/` (CSV
exportados) e `intentos/` (fotos de accesos rechazados).

---

## 5. Cómo funciona

### Reconocimiento

1. Cada foto de `Socios/` se convierte en un **vector de 128 números** que describe
   el rostro (`face_encodings`). Eso se hace una sola vez y se guarda en caché;
   por eso el arranque es lento la primera vez y rápido después.
2. De cada fotograma de la cámara se extraen los rostros y se calcula la
   **distancia euclídea** contra todos los socios (`face_distance`).
3. Gana el socio de menor distancia, siempre que esté por debajo de la
   **tolerancia** (`TOLERANCIA` en `config.py`, por defecto 0.50).
   Cuanto más baja, más estricto: menos falsos positivos, pero más veces que no
   reconoce a alguien que sí está cargado.

Para que el video vaya fluido, cada fotograma se reduce al 25 % antes de
procesarlo y se analiza 1 de cada 3 (`ESCALA_PROCESO` y `SALTEAR_FOTOGRAMAS`).

### Decisión de acceso

El reconocimiento responde *quién es*. El motor de `reglas.py` responde
*si puede entrar*. Cada regla tiene una condición, una decisión
(`RECHAZADO` o `ADVERTENCIA`) y un mensaje. Se evalúan en orden: el primer
rechazo corta, las advertencias se acumulan y dejan pasar.

| Regla | Verifica | Decisión |
|---|---|---|
| R1 | El socio está activo | Rechaza |
| R2 | El plan no está vencido | Rechaza |
| R3 | La hora entra en la franja del plan | Rechaza |
| R4 | Queda saldo en la bolsa de horas | Rechaza |
| R5 | No se supera el aforo | Rechaza |
| R6 | Avisa que ya se factura excedente | Advierte |
| R7 | Avisa que quedan pocas horas | Advierte |
| R8 | Avisa que el plan está por vencer | Advierte |
| R9 | Recuerda la reserva de sala del día | Advierte |

Para agregar una regla nueva no hay que tocar el resto del sistema: se suma un
diccionario a `BASE_CONOCIMIENTO`.

### Entrada y salida

La misma cámara sirve para las dos cosas. Si el socio no tiene una sesión
abierta, se le registra la **entrada**; si ya está adentro, se le registra la
**salida** y se calculan las horas, descontándolas de su bolsa y guardando como
excedente lo que la supere.

Para que no fiche diez veces mientras está parado frente a la cámara, después de
cada registro el sistema lo ignora durante 20 segundos (`SEGUNDOS_ESPERA`).
Las sesiones que quedan abiertas de días anteriores se cierran solas al arrancar.

---

## 6. Diferencias con el código base de la cátedra

| Código base | Este sistema |
|---|---|
| Toma **una sola foto** y termina | Video en tiempo real hasta que se presiona Q |
| Registra a cada persona **una vez para siempre** | Registra cada entrada y salida, todos los días |
| Guarda en un CSV plano | Base de datos SQLite, exportable a CSV |
| Solo registra | Decide si habilita el ingreso y explica por qué |
| Las fotos se copian a mano en la carpeta | Alta de socios desde el sistema con la cámara |
| Recodifica todas las fotos en cada arranque | Caché de codificaciones |
| `cv2.CAP_DSHOW`, solo Windows | Funciona en Windows, Linux y Mac |
| Si una foto no tiene rostro, el programa se cae | Avisa cuáles fallaron y sigue |

---

## 7. Limitación conocida

El sistema se puede engañar mostrando una **foto impresa o en la pantalla del
celular**: compara rasgos faciales, no verifica que haya una persona viva.
Resolverlo requiere detección de vida (pedir un parpadeo o un giro de cabeza),
que queda fuera del alcance de este trabajo. Conviene mencionarlo en la defensa:
es una limitación real de todos los sistemas de reconocimiento facial simples.

Además, la precisión baja con poca luz, con la cara muy de costado o con
barbijo, y las fotos de alta deben ser de frente y bien iluminadas.
