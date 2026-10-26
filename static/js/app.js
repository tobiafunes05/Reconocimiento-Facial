/**
 * COWORKING FACIAL - Frontend Application Logic
 * Integración de API, WebRTC Camera, Chart.js y Motor de Reglas
 */

const API = {
  estado: '/api/estado',
  presentes: '/api/presentes',
  socios: '/api/socios',
  altaSocio: '/api/socios/alta',
  renovarSocio: (id) => `/api/socios/${id}/renovar`,
  bajaSocio: (id) => `/api/socios/${id}/baja`,
  simularAcceso: '/api/acceso/simular',
  checkoutManual: '/api/acceso/checkout_manual',
  consumo: '/api/consumo',
  ocupacion: '/api/ocupacion',
  historial: '/api/historial',
  intentos: '/api/intentos',
  reglas: '/api/reglas',
  evaluarReglas: '/api/reglas/evaluar',
  recargarDemo: '/api/demo/recargar',
  reservas: '/api/reservas',
  comparar: '/api/comparar'
};

// Estado global de la aplicación
const AppState = {
  currentView: 'dashboard',
  sociosList: [],
  presentesList: [],
  reservasList: [],
  chartInstance: null,
  webcamStream: null,
  capturedPhotoBase64: null,
  autoRefreshInterval: null
};

// ==========================================================
// INICIALIZACIÓN
// ==========================================================
document.addEventListener('DOMContentLoaded', () => {
  initNavigation();
  initAutoRefresh();
  loadDashboardData();
  setupEventListeners();
});

// ==========================================================
// NAVEGACIÓN Y VISTAS
// ==========================================================
function initNavigation() {
  const navItems = document.querySelectorAll('.nav-item');
  navItems.forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const targetView = item.getAttribute('data-view');
      switchView(targetView);
    });
  });
}

function switchView(viewName) {
  AppState.currentView = viewName;

  // Actualizar Sidebar
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('active', el.getAttribute('data-view') === viewName);
  });

  // Mostrar Sección
  document.querySelectorAll('.view-section').forEach(sec => {
    sec.classList.remove('active');
  });

  const activeSec = document.getElementById(`view-${viewName}`);
  if (activeSec) {
    activeSec.classList.add('active');
  }

  // Título de la Topbar
  const titles = {
    dashboard: 'Panel de Control y Aforo en Vivo',
    kiosco: 'Kiosco de Acceso Biométrico Facial',
    socios: 'Padrón de Socios y Membresías',
    alta: 'Alta de Nuevo Socio',
    reservas: 'Gestión de Reservas de Salas (HU-09)',
    consumo: 'Reporte de Consumo y Facturación',
    ocupacion: 'Métricas de Ocupación y Analítica',
    reglas: 'Base de Conocimiento y Motor de Reglas (IA)',
    comparador: 'Verificación Biométrica y Calibración (CU-07)'
  };
  document.getElementById('topbar-page-title').textContent = titles[viewName] || 'Sistema de Control';

  // Cargas específicas por vista
  if (viewName === 'dashboard') loadDashboardData();
  if (viewName === 'kiosco') startKioskMode();
  if (viewName === 'socios') loadSociosList();
  if (viewName === 'alta') startAltaWebcam();
  if (viewName === 'reservas') loadReservas();
  if (viewName === 'consumo') loadConsumoData();
  if (viewName === 'ocupacion') loadOcupacionChart();
  if (viewName === 'reglas') loadReglasSandbox();
  if (viewName === 'comparador') initComparadorView();
}

// ==========================================================
// POLLING AUTOMÁTICO DE ESTADO (REFRESCO SUAVE)
// ==========================================================
function initAutoRefresh() {
  if (AppState.autoRefreshInterval) clearInterval(AppState.autoRefreshInterval);
  AppState.autoRefreshInterval = setInterval(() => {
    if (AppState.currentView === 'dashboard') {
      loadDashboardData(false);
    } else if (AppState.currentView === 'kiosco') {
      loadPresentesSummary();
    }
  }, 5000);
}

// ==========================================================
// CARGA DEL DASHBOARD
// ==========================================================
async function loadDashboardData(showLoading = true) {
  try {
    const [resEstado, resPresentes] = await Promise.all([
      fetch(API.estado).then(r => r.json()),
      fetch(API.presentes).then(r => r.json())
    ]);

    // Actualizar KPIs
    document.getElementById('kpi-ocupacion').textContent = `${resEstado.ocupacion_actual} / ${resEstado.aforo_maximo}`;
    document.getElementById('kpi-porcentaje').textContent = `${resEstado.porcentaje_ocupacion}% de capacidad`;
    document.getElementById('kpi-socios').textContent = resEstado.total_socios_activos;
    document.getElementById('kpi-sesiones-hoy').textContent = resEstado.sesiones_hoy;
    document.getElementById('kpi-facturacion').textContent = `$${resEstado.facturacion_mes.toLocaleString('es-AR')}`;

    // Actualizar Lista de Presentes en Coworking
    AppState.presentesList = resPresentes;
    renderPresentesTable(resPresentes);

    // Cargar selector de simulación rápida
    loadSimulationSelect();

    // Cargar reservas del día (HU-09)
    loadDashboardReservas();

  } catch (err) {
    console.error('Error cargando datos del dashboard:', err);
  }
}

async function loadDashboardReservas() {
  try {
    const res = await fetch(API.reservas);
    const reservas = await res.json();
    const countBadge = document.getElementById('dashboard-reservas-count');
    const tbody = document.getElementById('dashboard-reservas-tbody');

    if (countBadge) countBadge.textContent = `${reservas.length} programadas`;
    if (!tbody) return;

    if (reservas.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="4" style="text-align: center; padding: 24px; color: var(--text-dim);">
            No hay reservas de sala agendadas para el día de hoy.
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = reservas.map(r => `
      <tr>
        <td>
          <div style="font-weight: 600; color: #fff;">${r.socio_nombre}</div>
          <div style="font-size: 0.75rem; color: var(--text-dim);">${r.plan}</div>
        </td>
        <td><span class="plan-badge plan-libre">${r.sala}</span></td>
        <td style="font-family: 'JetBrains Mono', monospace; font-weight: 600; color: #818cf8;">
          ${r.hora_desde} a ${r.hora_hasta} hs
        </td>
        <td>
          <span class="status-badge por_vencer" style="font-size: 0.72rem;">
            RN-09 Recordatorio al Ingresar
          </span>
        </td>
      </tr>
    `).join('');
  } catch (e) {
    console.error('Error cargando reservas del dashboard:', e);
  }
}

function renderPresentesTable(presentes) {
  const tbody = document.getElementById('presentes-tbody');
  const countBadge = document.getElementById('presentes-count-badge');
  if (countBadge) countBadge.textContent = `${presentes.length} adentro`;

  if (!tbody) return;

  if (presentes.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="5" style="text-align: center; padding: 30px; color: var(--text-dim);">
          No hay socios en el coworking en este momento.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = presentes.map(p => `
    <tr>
      <td>
        <div class="user-cell">
          ${p.foto_url 
            ? `<img src="${p.foto_url}" class="user-avatar" alt="${p.nombre}">` 
            : `<div class="user-avatar">${p.nombre.substring(0, 2).toUpperCase()}</div>`}
          <div>
            <div class="user-name">${p.nombre}</div>
            <div class="user-sub">Ingreso: ${p.hora_entrada} hs</div>
          </div>
        </div>
      </td>
      <td>
        <span class="plan-badge plan-${p.plan}">${p.plan_nombre}</span>
      </td>
      <td>
        <span style="font-weight: 600; color: #38bdf8;">${p.tiempo_transcurrido}</span>
      </td>
      <td>
        <span style="font-family: 'JetBrains Mono', monospace;">${p.horas.toFixed(2)} h</span>
      </td>
      <td style="text-align: right;">
        <button class="btn-secondary" style="padding: 6px 12px; font-size: 0.78rem;" onclick="ejecutarCheckoutManual(${p.registro_id})">
          Registrar Salida
        </button>
      </td>
    </tr>
  `).join('');
}

// ==========================================================
// SIMULADOR DE ACCESO FACIAL (BOTÓN RÁPIDO Y CARGA FOTOGRÁFICA)
// ==========================================================
async function loadSimulationSelect() {
  try {
    const res = await fetch(API.socios);
    const socios = await res.json();
    AppState.sociosList = socios;

    const select = document.getElementById('simular-socio-select');
    if (!select) return;

    select.innerHTML = '<option value="">-- Seleccionar Socio para Simular Detección --</option>' +
      socios.map(s => `<option value="${s.nombre}">${s.nombre} (${s.plan_nombre})</option>`).join('');
  } catch (e) {
    console.error(e);
  }
}

async function simularPasoFacial(nombre = null) {
  const socioNombre = nombre || document.getElementById('simular-socio-select')?.value;
  if (!socioNombre) {
    showToast('Por favor seleccioná un socio para simular', 'warning');
    return;
  }

  try {
    const res = await fetch(API.simularAcceso, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nombre: socioNombre })
    });
    const data = await res.json();

    mostrarVeredictoKiosco(data);
    loadDashboardData(false);

    if (data.decision === 'HABILITADO') {
      showToast(`Acceso exitoso: ${data.etiqueta}`, 'success');
    } else if (data.decision === 'ADVERTENCIA') {
      showToast(`Advertencia: ${data.detalle}`, 'warning');
    } else {
      showToast(`Acceso denegado: ${data.motivo}`, 'error');
    }
  } catch (err) {
    showToast('Error al procesar simulación', 'error');
  }
}

function mostrarVeredictoKiosco(data) {
  const card = document.getElementById('kiosk-verdict-card');
  const icon = document.getElementById('kiosk-verdict-icon');
  const title = document.getElementById('kiosk-verdict-title');
  const detail = document.getElementById('kiosk-verdict-detail');

  if (!card) return;

  card.className = `verdict-card ${data.decision}`;

  if (data.decision === 'HABILITADO') {
    icon.innerHTML = `<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`;
    title.textContent = data.etiqueta || `HOLA ${data.nombre}`;
    detail.textContent = data.detalle || (data.tipo_movimiento === 'SALIDA' ? 'Salida registrada' : 'Ingreso habilitado');
  } else if (data.decision === 'ADVERTENCIA') {
    icon.innerHTML = `<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`;
    title.textContent = data.etiqueta || `ADVERTENCIA: ${data.nombre}`;
    detail.textContent = data.detalle || 'Ingreso permitido con aviso';
  } else {
    icon.innerHTML = `<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`;
    title.textContent = data.etiqueta || `ACCESO RECHAZADO`;
    detail.textContent = data.motivo || 'Motivo de rechazo por motor de reglas';
  }
}

// Checkout manual
async function ejecutarCheckoutManual(registroId) {
  if (!confirm('¿Registrar salida para esta persona?')) return;
  try {
    const res = await fetch(API.checkoutManual, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ registro_id: registroId })
    });
    const d = await res.json();
    if (res.ok) {
      showToast(d.mensaje, 'success');
      loadDashboardData(false);
    } else {
      showToast(d.error, 'error');
    }
  } catch (e) {
    showToast('Error al registrar salida', 'error');
  }
}

// ==========================================================
// KIOSCO FACIAL (CÁMARA WEBRTC / SIMULADOR FOTOGRÁFICO)
// ==========================================================
async function startKioskMode() {
  loadSimulationSelect();
  loadPresentesSummary();
}

async function loadPresentesSummary() {
  try {
    const res = await fetch(API.presentes);
    const pres = await res.json();
    const countEl = document.getElementById('kiosk-aforo-count');
    if (countEl) countEl.textContent = `${pres.length}`;
  } catch (e) {}
}

async function subirFotoSimulacion(file) {
  if (!file) return;
  const formData = new FormData();
  formData.append('foto', file);

  showToast('Analizando biometría facial...', 'warning');

  try {
    const res = await fetch(API.simularAcceso, {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    mostrarVeredictoKiosco(data);
    loadDashboardData(false);
    if (data.decision === 'HABILITADO') {
      showToast(data.etiqueta, 'success');
    } else if (data.decision === 'ADVERTENCIA') {
      showToast(data.detalle, 'warning');
    } else {
      showToast(data.motivo, 'error');
    }
  } catch (e) {
    showToast('Error al enviar fotografía para reconocimiento', 'error');
  }
}

// ==========================================================
// PADRÓN DE SOCIOS
// ==========================================================
async function loadSociosList() {
  const container = document.getElementById('socios-grid');
  if (!container) return;

  container.innerHTML = '<div style="color: var(--text-dim); padding: 40px; text-align: center;">Cargando padrón...</div>';

  try {
    const res = await fetch(API.socios);
    const socios = await res.json();
    AppState.sociosList = socios;
    renderSociosGrid(socios);
  } catch (e) {
    container.innerHTML = '<div style="color: var(--danger); padding: 40px; text-align: center;">Error al cargar padrón</div>';
  }
}

function renderSociosGrid(socios) {
  const container = document.getElementById('socios-grid');
  if (!container) return;

  if (socios.length === 0) {
    container.innerHTML = '<div style="color: var(--text-dim); text-align: center; padding: 40px;">No hay socios registrados.</div>';
    return;
  }

  container.innerHTML = socios.map(s => `
    <div class="panel-card" style="padding: 22px; position: relative;">
      <div style="display: flex; gap: 16px; align-items: center; margin-bottom: 16px;">
        ${s.foto_url 
          ? `<img src="${s.foto_url}" style="width: 58px; height: 58px; border-radius: 16px; object-fit: cover; border: 2px solid var(--border-subtle);">` 
          : `<div style="width: 58px; height: 58px; border-radius: 16px; background: #1f293d; display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 1.2rem; color: #818cf8;">${s.nombre.substring(0, 2).toUpperCase()}</div>`}
        <div>
          <div style="font-weight: 700; font-size: 1.05rem; color: #fff;">${s.nombre}</div>
          <div style="display: flex; gap: 8px; margin-top: 4px; align-items: center;">
            <span class="plan-badge plan-${s.plan}">${s.plan_nombre}</span>
            <span class="status-badge ${s.estado_codigo}">${s.estado_texto}</span>
          </div>
        </div>
      </div>

      <div style="background: rgba(0,0,0,0.25); border-radius: var(--radius-sm); padding: 14px; margin-bottom: 16px;">
        <div style="display: flex; justify-content: space-between; font-size: 0.8rem; margin-bottom: 6px;">
          <span style="color: var(--text-dim);">Consumo mensual</span>
          <span style="font-weight: 700; color: #fff;">
            ${s.horas_incluidas ? `${s.horas_usadas} / ${s.horas_incluidas} h` : `${s.horas_usadas} h (Ilimitado)`}
          </span>
        </div>
        ${s.horas_incluidas ? `
          <div class="progress-container" style="width: 100%;">
            <div class="progress-bar ${s.porcentaje_horas >= 90 ? 'warning' : ''}" style="width: ${s.porcentaje_horas}%;"></div>
          </div>
        ` : ''}
        <div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--text-dim); margin-top: 10px;">
          <span>Vence: ${s.vence}</span>
          <span>${s.dias_restantes >= 0 ? `${s.dias_restantes} días rest.` : 'Expirado'}</span>
        </div>
      </div>

      <div style="display: flex; gap: 8px;">
        <button class="btn-secondary" style="flex: 1; padding: 8px; font-size: 0.78rem; justify-content: center;" onclick="abrirModalRenovar(${s.id}, '${s.nombre}', '${s.plan}')">
          Renovar Plan
        </button>
        <button class="btn-danger" style="padding: 8px 12px; font-size: 0.78rem;" title="Eliminar socio del sistema" onclick="darDeBajaSocio(${s.id}, '${s.nombre}')">
          Eliminar
        </button>
      </div>
    </div>
  `).join('');
}

function filtrarSocios() {
  const query = document.getElementById('buscar-socio-input')?.value.toLowerCase() || '';
  const filtrados = AppState.sociosList.filter(s => 
    s.nombre.toLowerCase().includes(query) || s.plan_nombre.toLowerCase().includes(query)
  );
  renderSociosGrid(filtrados);
}

// Modal Renovar
function abrirModalRenovar(id, nombre, planActual) {
  document.getElementById('renovar-socio-id').value = id;
  document.getElementById('renovar-socio-nombre').textContent = nombre;
  document.getElementById('renovar-plan-select').value = planActual;
  document.getElementById('modal-renovar').classList.add('active');
}

function cerrarModalRenovar() {
  document.getElementById('modal-renovar').classList.remove('active');
}

async function confirmarRenovacion() {
  const id = document.getElementById('renovar-socio-id').value;
  const plan = document.getElementById('renovar-plan-select').value;
  const dias = document.getElementById('renovar-dias-input').value;

  try {
    const res = await fetch(API.renovarSocio(id), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan, dias })
    });
    const d = await res.json();
    cerrarModalRenovar();
    showToast(d.mensaje, 'success');
    loadSociosList();
  } catch (e) {
    showToast('Error al renovar plan', 'error');
  }
}

async function darDeBajaSocio(id, nombre) {
  if (!confirm(`¿Eliminar definitivamente a "${nombre}"? Se borrarán sus datos, registros y fotografía del sistema facial.`)) return;
  try {
    const res = await fetch(API.bajaSocio(id), { method: 'POST' });
    const d = await res.json();
    showToast(d.mensaje, 'success');
    loadSociosList();
    loadDashboardData(false);
  } catch (e) {
    showToast('Error al eliminar socio', 'error');
  }
}

// ==========================================================
// ALTA DE SOCIO (WEBCAM INTEGRADA + FORMULARIO)
// ==========================================================
async function startAltaWebcam() {
  const video = document.getElementById('alta-webcam-preview');
  if (!video) return;

  try {
    if (AppState.webcamStream) {
      AppState.webcamStream.getTracks().forEach(t => t.stop());
    }
    const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
    AppState.webcamStream = stream;
    video.srcObject = stream;
    document.getElementById('alta-cam-placeholder')?.style.setProperty('display', 'none');
    video.style.display = 'block';
  } catch (err) {
    console.log('No se pudo acceder a la cámara web en el navegador, se usará subida manual:', err);
    document.getElementById('alta-cam-placeholder')?.style.setProperty('display', 'flex');
  }
}

function capturarFotoWebcam() {
  const video = document.getElementById('alta-webcam-preview');
  const canvas = document.createElement('canvas');
  canvas.width = 640;
  canvas.height = 480;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, 640, 480);

  const b64 = canvas.toDataURL('image/jpeg', 0.9);
  AppState.capturedPhotoBase64 = b64;

  const previewImg = document.getElementById('alta-foto-snapshot');
  if (previewImg) {
    previewImg.src = b64;
    previewImg.style.display = 'block';
    video.style.display = 'none';
  }
  document.getElementById('btn-retake-photo').style.display = 'inline-flex';
  document.getElementById('btn-capture-photo').style.display = 'none';
  showToast('Fotografía capturada con éxito', 'success');
}

function retomarFotoWebcam() {
  AppState.capturedPhotoBase64 = null;
  const video = document.getElementById('alta-webcam-preview');
  const previewImg = document.getElementById('alta-foto-snapshot');
  if (previewImg) previewImg.style.display = 'none';
  if (video) video.style.display = 'block';
  document.getElementById('btn-retake-photo').style.display = 'none';
  document.getElementById('btn-capture-photo').style.display = 'inline-flex';
}

async function registrarNuevoSocio(e) {
  e.preventDefault();
  const nombre = document.getElementById('alta-nombre').value.trim();
  const plan = document.getElementById('alta-plan').value;
  const dias = document.getElementById('alta-dias').value;
  const fileInput = document.getElementById('alta-file-input');

  if (!nombre) {
    showToast('El nombre del socio es obligatorio', 'warning');
    return;
  }

  const formData = new FormData();
  formData.append('nombre', nombre);
  formData.append('plan', plan);
  formData.append('dias', dias);

  if (AppState.capturedPhotoBase64) {
    formData.append('foto_b64', AppState.capturedPhotoBase64);
  } else if (fileInput.files.length > 0) {
    formData.append('foto', fileInput.files[0]);
  }

  showToast('Registrando socio y codificando biometría...', 'warning');

  try {
    const res = await fetch(API.altaSocio, {
      method: 'POST',
      body: formData
    });
    const d = await res.json();
    if (res.ok) {
      showToast(d.mensaje, 'success');
      document.getElementById('form-alta-socio').reset();
      retomarFotoWebcam();
      switchView('socios');
    } else {
      showToast(d.error || 'Error al registrar', 'error');
    }
  } catch (err) {
    showToast('Error en la comunicación con el servidor', 'error');
  }
}

// ==========================================================
// CONSUMO Y FACTURACIÓN
// ==========================================================
async function loadConsumoData() {
  try {
    const res = await fetch(API.consumo);
    const data = await res.json();

    document.getElementById('consumo-total-facturar').textContent = `$${data.total_facturar.toLocaleString('es-AR')}`;
    document.getElementById('consumo-total-horas').textContent = `${data.total_horas} hs`;
    document.getElementById('consumo-total-sesiones').textContent = data.total_sesiones;

    const tbody = document.getElementById('consumo-tbody');
    if (!tbody) return;

    tbody.innerHTML = data.socios.map(s => `
      <tr>
        <td>
          <div style="font-weight: 600; color: #fff;">${s.nombre}</div>
          <div style="font-size: 0.75rem; color: var(--text-dim);">Vence: ${s.vence}</div>
        </td>
        <td>
          <span class="plan-badge plan-${s.plan}">${s.plan_nombre}</span>
        </td>
        <td style="text-align: center;">${s.sesiones}</td>
        <td style="text-align: right; font-family: 'JetBrains Mono', monospace;">${s.horas.toFixed(1)} h</td>
        <td style="text-align: right; font-family: 'JetBrains Mono', monospace; color: ${s.excedente > 0 ? '#fb7185' : 'var(--text-dim)'};">
          ${s.excedente > 0 ? `+${s.excedente.toFixed(1)} h` : '0.0 h'}
        </td>
        <td style="text-align: right; font-weight: 700; color: ${s.importe > 0 ? '#34d399' : 'var(--text-muted)'};">
          $${s.importe.toLocaleString('es-AR')}
        </td>
      </tr>
    `).join('');
  } catch (e) {
    console.error(e);
  }
}

// ==========================================================
// OCUPACIÓN Y GRÁFICO (CHART.JS)
// ==========================================================
async function loadOcupacionChart() {
  try {
    const [resOcup, resHist, resRechazados] = await Promise.all([
      fetch(API.ocupacion).then(r => r.json()),
      fetch(API.historial).then(r => r.json()),
      fetch(API.intentos).then(r => r.json())
    ]);

    document.getElementById('ocupacion-hora-pico').textContent = resOcup.hora_pico;
    document.getElementById('ocupacion-max-concurrencia').textContent = `${resOcup.max_concurrencia} personas`;

    // Render Chart.js
    const ctx = document.getElementById('ocupacion-canvas')?.getContext('2d');
    if (ctx) {
      if (AppState.chartInstance) AppState.chartInstance.destroy();

      // Gradiente de color
      const gradient = ctx.createLinearGradient(0, 0, 0, 300);
      gradient.addColorStop(0, 'rgba(99, 102, 241, 0.5)');
      gradient.addColorStop(1, 'rgba(99, 102, 241, 0.02)');

      AppState.chartInstance = new Chart(ctx, {
        type: 'line',
        data: {
          labels: resOcup.etiquetas,
          datasets: [{
            label: 'Ocupación por Hora',
            data: resOcup.valores,
            borderColor: '#6366f1',
            backgroundColor: gradient,
            borderWidth: 3,
            fill: true,
            tension: 0.35,
            pointBackgroundColor: '#818cf8',
            pointRadius: 4,
            pointHoverRadius: 6
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: '#111726',
              titleColor: '#fff',
              bodyColor: '#cbd5e1',
              borderColor: 'rgba(255,255,255,0.1)',
              borderWidth: 1,
              padding: 12
            }
          },
          scales: {
            x: {
              grid: { color: 'rgba(255,255,255,0.04)' },
              ticks: { color: '#64748b' }
            },
            y: {
              grid: { color: 'rgba(255,255,255,0.04)' },
              ticks: { color: '#64748b', stepSize: 1 },
              beginAtZero: true
            }
          }
        }
      });
    }

    // Render Historial
    const histTbody = document.getElementById('historial-tbody');
    if (histTbody) {
      histTbody.innerHTML = resHist.slice(0, 15).map(h => `
        <tr>
          <td><span style="font-weight: 600; color: #fff;">${h.nombre}</span></td>
          <td><span class="plan-badge plan-${h.plan}">${h.plan_nombre}</span></td>
          <td style="font-size: 0.8rem; color: var(--text-dim);">${h.entrada}</td>
          <td style="font-size: 0.8rem; color: var(--text-dim);">${h.salida}</td>
          <td style="font-family: 'JetBrains Mono', monospace;">${h.horas !== null ? `${h.horas.toFixed(2)} h` : 'En curso'}</td>
        </tr>
      `).join('');
    }

    // Render Rechazados (HU-11 / CU-06)
    const rechTbody = document.getElementById('rechazados-tbody');
    if (rechTbody) {
      rechTbody.innerHTML = resRechazados.length ? resRechazados.map(r => `
        <tr>
          <td>
            ${r.foto_url ? `
              <img src="${r.foto_url}" alt="Rostro" 
                   style="width: 36px; height: 36px; border-radius: 6px; object-fit: cover; border: 1px solid rgba(251, 113, 133, 0.4); cursor: pointer;"
                   onclick="verFotoIntento('${r.foto_url}', '${r.nombre}', '${r.motivo}', '${r.momento}')"
                   title="Click para ampliar imagen">
            ` : `
              <div style="width: 36px; height: 36px; border-radius: 6px; background: rgba(255,255,255,0.05); display: flex; align-items: center; justify-content: center; font-size: 0.65rem; color: var(--text-dim);">
                S/F
              </div>
            `}
          </td>
          <td style="font-size: 0.8rem; color: var(--text-dim);">${r.momento}</td>
          <td><span style="font-weight: 600; color: #fb7185;">${r.nombre}</span></td>
          <td style="color: var(--text-muted);">${r.motivo}</td>
        </tr>
      `).join('') : `<tr><td colspan="4" style="text-align: center; color: var(--text-dim); padding: 20px;">Sin rechazos registrados</td></tr>`;
    }

  } catch (e) {
    console.error(e);
  }
}

function verFotoIntento(url, nombre, motivo, momento) {
  const modal = document.getElementById('modal-foto-intento');
  const img = document.getElementById('modal-foto-intento-img');
  const desc = document.getElementById('modal-foto-intento-desc');
  const title = document.getElementById('modal-foto-intento-title');

  if (modal && img && desc) {
    img.src = url;
    if (title) title.textContent = `Registro Facial: ${nombre}`;
    desc.innerHTML = `<strong>Motivo:</strong> ${motivo}<br><span style="color: var(--text-dim);">${momento}</span>`;
    modal.classList.add('active');
  }
}

function cerrarModalFotoIntento() {
  document.getElementById('modal-foto-intento')?.classList.remove('active');
}

// ==========================================================
// MOTOR DE REGLAS Y SANDBOX ACADÉMICO
// ==========================================================
async function loadReglasSandbox() {
  try {
    const [resReglas, resSocios] = await Promise.all([
      fetch(API.reglas).then(r => r.json()),
      fetch(API.socios).then(r => r.json())
    ]);

    const select = document.getElementById('sandbox-socio-select');
    if (select) {
      select.innerHTML = resSocios.map(s => `
        <option value="${s.nombre}">${s.nombre} (${s.plan_nombre})</option>
      `).join('');
    }

    renderReglasList(resReglas);
    evaluarReglasSandbox();
  } catch (e) {
    console.error(e);
  }
}

function renderReglasList(reglas, evaluaciones = null) {
  const container = document.getElementById('reglas-lista-container');
  if (!container) return;

  container.innerHTML = reglas.map(r => {
    const evalData = evaluaciones ? evaluaciones.find(e => e.codigo === r.codigo) : null;
    const triggered = evalData && evalData.se_cumple;
    const triggeredClass = triggered ? `triggered-${r.decision}` : '';

    return `
      <div class="rule-box ${triggeredClass}">
        <div class="rule-header">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span class="rule-code" style="font-weight: 800; color: #818cf8;">${r.codigo}</span>
            ${r.historia ? `<span style="font-size: 0.72rem; padding: 2px 6px; border-radius: 4px; background: rgba(99,102,241,0.15); color: #c7d2fe; font-weight: 600;">${r.historia}</span>` : ''}
          </div>
          <span class="status-badge ${r.decision === 'RECHAZADO' ? 'vencido' : 'por_vencer'}">
            ${r.decision}
          </span>
        </div>
        <div class="rule-desc">${r.descripcion}</div>
        ${triggered && evalData.mensaje ? `
          <div class="rule-message ${r.decision}">
            [ACTIVADA]: ${evalData.mensaje}
          </div>
        ` : ''}
      </div>
    `;
  }).join('');
}

async function evaluarReglasSandbox() {
  const nombre = document.getElementById('sandbox-socio-select')?.value;
  if (!nombre) return;

  const hora = document.getElementById('sandbox-hora')?.value || 12;
  const aforo = document.getElementById('sandbox-aforo')?.value || 5;
  const horas_usadas = document.getElementById('sandbox-horas-usadas')?.value || 0;
  const activo = document.getElementById('sandbox-activo')?.checked;
  const tiene_reserva = document.getElementById('sandbox-reserva')?.checked;

  try {
    const res = await fetch(API.evaluarReglas, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nombre, hora, adentro: aforo, horas_usadas, activo, tiene_reserva })
    });
    const d = await res.json();

    // Actualizar indicador de resolución
    const resolucionCard = document.getElementById('sandbox-resolucion-card');
    const resolucionTitle = document.getElementById('sandbox-resolucion-title');
    const resolucionMotivo = document.getElementById('sandbox-resolucion-motivo');

    resolucionCard.className = `verdict-card ${d.decision_final}`;
    resolucionTitle.textContent = d.decision_final === 'HABILITADO' ? 'ACCESO HABILITADO' : d.decision_final;
    resolucionMotivo.textContent = d.motivo_final || 'Cumple con todas las condiciones del sistema.';

    // Re-render reglas marcando cuáles se cumplieron
    const reglasBase = await fetch(API.reglas).then(r => r.json());
    renderReglasList(reglasBase, d.evaluaciones);

  } catch (e) {
    console.error(e);
  }
}

// ==========================================================
// GESTIÓN DE RESERVAS DE SALAS (HU-09 / RN-09)
// ==========================================================
async function loadReservas() {
  try {
    const [resReservas, resSocios] = await Promise.all([
      fetch(API.reservas).then(r => r.json()),
      fetch(API.socios).then(r => r.json())
    ]);

    // Llenar selector de socios
    const select = document.getElementById('reserva-socio-select');
    if (select) {
      select.innerHTML = resSocios.map(s => `
        <option value="${s.id}">${s.nombre} (${s.plan_nombre})</option>
      `).join('');
    }

    // Setear fecha por defecto a hoy
    const fechaInput = document.getElementById('reserva-fecha');
    if (fechaInput && !fechaInput.value) {
      const hoy = new Date().toISOString().split('T')[0];
      fechaInput.value = hoy;
    }

    // Render tabla de reservas
    const tbody = document.getElementById('reservas-tbody');
    if (!tbody) return;

    if (resReservas.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="5" style="text-align: center; padding: 30px; color: var(--text-dim);">
            No hay reservas programadas actualmente.
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = resReservas.map(r => `
      <tr>
        <td>
          <div style="font-weight: 600; color: #fff;">${r.socio_nombre}</div>
          <div style="font-size: 0.75rem; color: var(--text-dim);">${r.plan}</div>
        </td>
        <td><span class="plan-badge plan-libre">${r.sala}</span></td>
        <td style="font-size: 0.82rem; color: var(--text-muted);">${r.fecha}</td>
        <td style="font-family: 'JetBrains Mono', monospace; font-weight: 600; color: #818cf8;">
          ${r.hora_desde} a ${r.hora_hasta} hs
        </td>
        <td>
          <span class="status-badge vigente" style="font-size: 0.72rem;">
            Aviso automático al entrar
          </span>
        </td>
      </tr>
    `).join('');

  } catch (e) {
    console.error('Error cargando reservas:', e);
  }
}

async function registrarNuevaReserva(e) {
  e.preventDefault();
  const socio_id = document.getElementById('reserva-socio-select')?.value;
  const sala = document.getElementById('reserva-sala-select')?.value;
  const fecha = document.getElementById('reserva-fecha')?.value;
  const hora_desde = document.getElementById('reserva-desde')?.value;
  const hora_hasta = document.getElementById('reserva-hasta')?.value;

  if (!socio_id || !sala || !fecha || !hora_desde || !hora_hasta) {
    showToast('Complete todos los campos de la reserva', 'warning');
    return;
  }

  try {
    const res = await fetch(API.reservas, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ socio_id, sala, fecha, hora_desde, hora_hasta })
    });
    const d = await res.json();
    if (res.ok) {
      showToast('Reserva de sala confirmada exitosamente', 'success');
      loadReservas();
      loadDashboardReservas();
    } else {
      showToast(d.error || 'Error al crear reserva', 'error');
    }
  } catch (err) {
    showToast('Error de conexión', 'error');
  }
}

// ==========================================================
// COMPARADOR FACIAL BIOMÉTRICO (CU-07)
// ==========================================================
let compFileA = null;
let compFileB = null;

async function initComparadorView() {
  try {
    const res = await fetch(API.socios);
    const socios = await res.json();

    const selectA = document.getElementById('comp-socio-a');
    const selectB = document.getElementById('comp-socio-b');

    const opciones = '<option value="">-- O subir archivo abajo --</option>' + socios.map(s => `
      <option value="${s.nombre}">${s.nombre} (${s.plan_nombre})</option>
    `).join('');

    if (selectA) selectA.innerHTML = opciones;
    if (selectB) selectB.innerHTML = opciones;

    // Seleccionar por defecto dos socios para prueba inmediata
    if (socios.length >= 2) {
      if (selectA) {
        selectA.value = socios[0].nombre;
        previewComparadorSocio('a', socios[0].nombre);
      }
      if (selectB) {
        selectB.value = socios[1].nombre;
        previewComparadorSocio('b', socios[1].nombre);
      }
    }
  } catch (e) {
    console.error('Error inicializando comparador:', e);
  }
}

function previewComparadorSocio(lado, nombre) {
  const img = document.getElementById(`comp-preview-${lado}`);
  const empty = document.getElementById(`comp-empty-${lado}`);
  if (!nombre) {
    if (img) img.style.display = 'none';
    if (empty) empty.style.display = 'block';
    return;
  }
  if (lado === 'a') compFileA = null;
  if (lado === 'b') compFileB = null;

  if (img) {
    img.src = `/fotos/socios/${nombre}.jpg`;
    img.style.display = 'block';
  }
  if (empty) empty.style.display = 'none';
}

function previewComparadorFile(lado, input) {
  const file = input.files[0];
  if (!file) return;

  if (lado === 'a') {
    compFileA = file;
    document.getElementById('comp-socio-a').value = '';
  } else {
    compFileB = file;
    document.getElementById('comp-socio-b').value = '';
  }

  const reader = new FileReader();
  reader.onload = (e) => {
    const img = document.getElementById(`comp-preview-${lado}`);
    const empty = document.getElementById(`comp-empty-${lado}`);
    if (img) {
      img.src = e.target.result;
      img.style.display = 'block';
    }
    if (empty) empty.style.display = 'none';
  };
  reader.readAsDataURL(file);
}

async function ejecutarComparacionBiometrica() {
  const socioA = document.getElementById('comp-socio-a')?.value;
  const socioB = document.getElementById('comp-socio-b')?.value;
  const tolerancia = document.getElementById('comp-tolerancia')?.value || 0.50;

  if (!socioA && !compFileA) {
    showToast('Seleccione o suba la primera imagen (Foto 1)', 'warning');
    return;
  }
  if (!socioB && !compFileB) {
    showToast('Seleccione o suba la segunda imagen (Foto 2)', 'warning');
    return;
  }

  const formData = new FormData();
  formData.append('tolerancia', tolerancia);

  if (compFileA) formData.append('foto_a', compFileA);
  else formData.append('socio_a', socioA);

  if (compFileB) formData.append('foto_b', compFileB);
  else formData.append('socio_b', socioB);

  showToast('Procesando vectores faciales de 128D...', 'info');

  try {
    const res = await fetch(API.comparar, {
      method: 'POST',
      body: formData
    });
    const d = await res.json();

    if (!res.ok) {
      showToast(d.error || 'Error en la comparación biométrica', 'error');
      return;
    }

    // Actualizar previsualizaciones con recuadros devueltos
    if (d.foto_a_b64) document.getElementById('comp-preview-a').src = d.foto_a_b64;
    if (d.foto_b_b64) document.getElementById('comp-preview-b').src = d.foto_b_b64;

    // Mostrar Veredicto
    const box = document.getElementById('comp-resultado-box');
    const card = document.getElementById('comp-verdict-card');
    const title = document.getElementById('comp-verdict-title');
    const detail = document.getElementById('comp-verdict-detail');

    if (box) box.style.display = 'block';
    if (card) card.className = `verdict-card ${d.decision}`;
    if (title) title.textContent = `${d.resultado} (Distancia: ${d.distancia.toFixed(4)})`;
    if (detail) detail.textContent = d.explicacion;

    showToast(`Comparación finalizada: Distancia ${d.distancia.toFixed(4)}`, d.coincide ? 'success' : 'warning');

  } catch (err) {
    console.error(err);
    showToast('Error al conectar con el servidor', 'error');
  }
}

// ==========================================================
// RECARGA DE DATOS DEMO
// ==========================================================
async function recargarDatosDemo() {
  if (!confirm('¿Desea recargar los 7 socios de prueba y el historial del mes?')) return;
  showToast('Restableciendo datos demo...', 'warning');
  try {
    const res = await fetch(API.recargarDemo, { method: 'POST' });
    const d = await res.json();
    showToast(d.mensaje, 'success');
    loadDashboardData();
  } catch (e) {
    showToast('Error al recargar datos demo', 'error');
  }
}

// ==========================================================
// TOAST NOTIFICACIONES
// ==========================================================
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <span>${message}</span>
  `;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// ==========================================================
// EVENT LISTENERS GENERALES
// ==========================================================
function setupEventListeners() {
  // Búsqueda en padrón
  document.getElementById('buscar-socio-input')?.addEventListener('input', filtrarSocios);

  // Formulario alta socio
  document.getElementById('form-alta-socio')?.addEventListener('submit', registrarNuevoSocio);

  // Formulario nueva reserva (HU-09)
  document.getElementById('form-crear-reserva')?.addEventListener('submit', registrarNuevaReserva);

  // Simulación de foto drag & drop o input
  const dropZone = document.getElementById('kiosk-drop-zone');
  const fileInput = document.getElementById('kiosk-file-input');

  if (dropZone && fileInput) {
    dropZone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (e) => {
      if (e.target.files.length) subirFotoSimulacion(e.target.files[0]);
    });
  }

  // Sandbox inputs
  ['sandbox-socio-select', 'sandbox-hora', 'sandbox-aforo', 'sandbox-horas-usadas', 'sandbox-activo', 'sandbox-reserva'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', evaluarReglasSandbox);
    document.getElementById(id)?.addEventListener('change', evaluarReglasSandbox);
  });
}
