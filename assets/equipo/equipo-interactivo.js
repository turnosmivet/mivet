// Foto del equipo interactiva: al pasar el cursor (o el dedo) sobre una persona,
// se resalta su silueta con un halo rosa, se oscurece el resto y aparece su nombre.
// Las siluetas son recortes PNG/WebP con transparencia; para saber qué persona está
// bajo el puntero se usa un "mapa" de baja resolución (cada píxel = índice de persona).

const BASE = '/mivet/assets/equipo/'

// Nombres en orden de izquierda a derecha en la foto.
const NOMBRES = ['Sole', 'Rocío', 'Majo', 'Sabri']

// Posiciones en % de la imagen: x/y/w/h = caja del recorte, hx/hy = punta de la cabeza.
const VARIANTES = {
  desktop: {
    w: 2000, h: 1116,
    personas: [
      { x: 18.9, y: 35.842, w: 19.05, h: 64.158, hx: 29.0, hy: 36.2 },
      { x: 36.3, y: 36.918, w: 16.9, h: 63.082, hx: 41.95, hy: 37.28 },
      { x: 49.45, y: 33.513, w: 17.0, h: 66.487, hx: 56.5, hy: 33.87 },
      { x: 64.1, y: 30.108, w: 19.2, h: 69.892, hx: 71.25, hy: 30.47 },
    ],
  },
  mobile: {
    w: 1116, h: 2000,
    personas: [
      { x: 0.0, y: 35.35, w: 29.48, h: 64.65, hx: 13.08, hy: 35.55 },
      { x: 22.76, y: 35.95, w: 33.602, h: 64.05, hx: 35.93, hy: 36.15 },
      { x: 48.118, y: 33.75, w: 32.706, h: 66.25, hx: 60.13, hy: 33.95 },
      { x: 75.269, y: 31.85, w: 24.731, h: 68.15, hx: 86.29, hy: 32.05 },
    ],
  },
}

// Escala del mapa respecto de la imagen y valor de gris por persona (índice * 60).
const MAPA_ESCALA = 4
const MAPA_PASO = 60

// Igual que el object-position anterior de la imagen (center 70%).
const POS_Y = 0.7
// Recorte lateral máximo (por lado) en pantallas angostas, para no cortar a las de los extremos.
// Si sobra alto, se ve de fondo una copia desenfocada de la foto.
const RECORTE_LATERAL_MAX = 0.05

const CSS = `
.eq-root{position:relative;width:100%;height:100%;overflow:hidden;background:#1b1418;
  -webkit-tap-highlight-color:transparent;touch-action:none;user-select:none;-webkit-user-select:none}
.eq-stage{position:absolute;left:0;top:0}
.eq-fondo{position:absolute;inset:-40px;width:calc(100% + 80px);height:calc(100% + 80px);object-fit:cover;filter:blur(24px) brightness(.8);pointer-events:none}
.eq-stage.eq-sobre{cursor:pointer}
.eq-stage img{position:absolute;display:block;pointer-events:none;-webkit-user-drag:none}
.eq-base{left:0;top:0;width:100%;height:100%}
.eq-dim{position:absolute;inset:0;background:rgba(18,8,16,.6);opacity:0;transition:opacity .35s ease;pointer-events:none}
.eq-root.eq-activa .eq-dim{opacity:1}
.eq-figura{opacity:0;transition:opacity .35s ease,filter .35s ease;filter:drop-shadow(0 0 0 rgba(255,92,170,0))}
.eq-figura.eq-on{opacity:1;filter:drop-shadow(0 0 3px rgba(255,170,215,.95)) drop-shadow(0 0 10px rgba(255,92,170,.9)) drop-shadow(0 0 26px rgba(255,64,160,.65));
  animation:eq-latido 2.4s ease-in-out .35s infinite}
@keyframes eq-latido{50%{filter:drop-shadow(0 0 4px rgba(255,170,215,1)) drop-shadow(0 0 14px rgba(255,92,170,.95)) drop-shadow(0 0 34px rgba(255,64,160,.75))}}
.eq-nombre{position:absolute;transform:translate(-50%,calc(-100% - 6px)) scale(.9);opacity:0;
  transition:opacity .3s ease,transform .3s ease;pointer-events:none;white-space:nowrap;
  font-family:"HelveticaNowDisplay-Medium",system-ui,sans-serif;font-size:clamp(15px,1.6vw,24px);color:#fff;
  padding:.35em .9em;border-radius:999px;background:rgba(255,64,160,.88);
  box-shadow:0 0 12px rgba(255,92,170,.8),0 0 28px rgba(255,64,160,.5)}
.eq-nombre.eq-on{opacity:1;transform:translate(-50%,calc(-100% - 14px)) scale(1)}
.eq-pista{position:absolute;left:50%;top:14px;transform:translateX(-50%);
  font-family:"HelveticaNowDisplayW01-Rg",system-ui,sans-serif;font-size:14px;color:#fff;white-space:nowrap;
  background:rgba(0,0,0,.45);padding:.45em 1em;border-radius:999px;pointer-events:none;transition:opacity .4s ease}
.eq-root.eq-usada .eq-pista{opacity:0}
.eq-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.eq-sr:focus-visible{outline:none}
@media (prefers-reduced-motion:reduce){.eq-figura,.eq-nombre,.eq-dim{transition:none}.eq-figura.eq-on{animation:none}}
`

function inyectarCss() {
  if (document.getElementById('eq-css')) return
  const s = document.createElement('style')
  s.id = 'eq-css'
  s.textContent = CSS
  document.head.appendChild(s)
}

function cargarMapa(src) {
  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => {
      const c = document.createElement('canvas')
      c.width = img.naturalWidth
      c.height = img.naturalHeight
      const ctx = c.getContext('2d', { willReadFrequently: true })
      ctx.drawImage(img, 0, 0)
      resolve({ w: c.width, h: c.height, data: ctx.getImageData(0, 0, c.width, c.height).data })
    }
    img.onerror = () => resolve(null)
    img.src = src
  })
}

function construir(root, clave, alEstado) {
  const v = VARIANTES[clave]
  const stage = document.createElement('div')
  stage.className = 'eq-stage'

  const base = document.createElement('img')
  base.className = 'eq-base'
  base.src = `${BASE}equipo-${clave}.webp`
  base.alt = `El equipo de MiVet: ${NOMBRES.join(', ')}, frente al cartel de neón de la clínica.`
  base.decoding = 'async'
  stage.appendChild(base)

  const dim = document.createElement('div')
  dim.className = 'eq-dim'
  stage.appendChild(dim)

  const figuras = []
  const nombres = []
  v.personas.forEach((p, i) => {
    const f = document.createElement('img')
    f.className = 'eq-figura'
    f.src = `${BASE}equipo-${clave}-${i + 1}.webp`
    f.alt = ''
    f.decoding = 'async'
    Object.assign(f.style, { left: `${p.x}%`, top: `${p.y}%`, width: `${p.w}%`, height: `${p.h}%` })
    stage.appendChild(f)
    figuras.push(f)

    const n = document.createElement('div')
    n.className = 'eq-nombre'
    n.textContent = NOMBRES[i]
    n.setAttribute('aria-hidden', 'true')
    Object.assign(n.style, { left: `${p.hx}%`, top: `${p.hy}%` })
    stage.appendChild(n)
    nombres.push(n)
  })

  // Botones invisibles para navegar con teclado / lectores de pantalla.
  v.personas.forEach((_, i) => {
    const b = document.createElement('button')
    b.type = 'button'
    b.className = 'eq-sr'
    b.textContent = NOMBRES[i]
    b.addEventListener('focus', () => alEstado(i))
    b.addEventListener('blur', () => alEstado(-1))
    stage.appendChild(b)
  })

  const fondo = document.createElement('img')
  fondo.className = 'eq-fondo'
  fondo.src = base.src
  fondo.alt = ''
  fondo.setAttribute('aria-hidden', 'true')
  root.appendChild(fondo)
  root.appendChild(stage)
  return { v, stage, figuras, nombres }
}

export function mount(contenedor) {
  if (!contenedor) return () => {}
  inyectarCss()

  const root = document.createElement('div')
  root.className = 'eq-root'
  const pista = document.createElement('div')
  pista.className = 'eq-pista'
  const tactil = window.matchMedia('(hover: none)').matches
  pista.textContent = tactil ? 'Tocá a cada una para conocerla' : 'Pasá el cursor para conocer al equipo'
  contenedor.appendChild(root)

  const mq = window.matchMedia('(max-width: 767px)')
  let vista = null
  let mapa = null
  let activa = -1
  let token = 0

  function setActiva(i) {
    if (!vista || i === activa) return
    activa = i
    vista.figuras.forEach((f, k) => f.classList.toggle('eq-on', k === i))
    vista.nombres.forEach((n, k) => n.classList.toggle('eq-on', k === i))
    root.classList.toggle('eq-activa', i >= 0)
    if (i >= 0) {
      root.classList.add('eq-usada')
      encuadrarNombre(i)
    }
  }

  function ajustar() {
    if (!vista) return
    const cw = root.clientWidth
    const ch = root.clientHeight
    const s = Math.max(cw / vista.v.w, Math.min(ch / vista.v.h, cw / (vista.v.w * (1 - 2 * RECORTE_LATERAL_MAX))))
    const sw = vista.v.w * s
    const sh = vista.v.h * s
    Object.assign(vista.stage.style, {
      width: `${sw}px`,
      height: `${sh}px`,
      left: `${(cw - sw) / 2}px`,
      top: `${(ch - sh) * (sh < ch ? 1 : POS_Y)}px`,
    })
    if (activa >= 0) encuadrarNombre(activa)
  }

  // Evita que la etiqueta del nombre se salga por los costados de la pantalla.
  function encuadrarNombre(i) {
    const n = vista.nombres[i]
    n.style.marginLeft = '0px'
    const r = n.getBoundingClientRect()
    const c = root.getBoundingClientRect()
    const m = 12
    let dx = 0
    if (r.left < c.left + m) dx = c.left + m - r.left
    else if (r.right > c.right - m) dx = c.right - m - r.right
    n.style.marginLeft = `${dx}px`
  }

  // Índice de la persona bajo el punto (coordenadas de pantalla), o -1.
  function personaEn(clientX, clientY) {
    if (!vista || !mapa) return -1
    const r = vista.stage.getBoundingClientRect()
    const u = (clientX - r.left) / r.width
    const t = (clientY - r.top) / r.height
    if (u < 0 || u >= 1 || t < 0 || t >= 1) return -1
    const x = Math.floor(u * mapa.w)
    const y = Math.floor(t * mapa.h)
    const val = mapa.data[(y * mapa.w + x) * 4]
    return Math.round(val / MAPA_PASO) - 1
  }

  async function montarVista() {
    const clave = mq.matches ? 'mobile' : 'desktop'
    const mio = ++token
    setActiva(-1)
    activa = -1
    root.replaceChildren()
    mapa = null
    vista = construir(root, clave, setActiva)
    root.appendChild(pista)
    ajustar()
    const m = await cargarMapa(`${BASE}equipo-${clave}-mapa.png`)
    if (mio === token) mapa = m
  }

  // Mouse: resalta mientras el cursor está encima.
  // Táctil: tocar (o deslizar el dedo) resalta; queda resaltada hasta tocar otra o fuera.
  let arrastrando = false
  function onMove(e) {
    if (e.pointerType === 'mouse') {
      const i = personaEn(e.clientX, e.clientY)
      vista.stage.classList.toggle('eq-sobre', i >= 0)
      setActiva(i)
    } else if (arrastrando) {
      const i = personaEn(e.clientX, e.clientY)
      if (i >= 0) setActiva(i)
    }
  }
  function onDown(e) {
    if (e.pointerType === 'mouse') return
    arrastrando = true
    const i = personaEn(e.clientX, e.clientY)
    setActiva(i === activa ? -1 : i)
  }
  function onUp() { arrastrando = false }
  function onLeave(e) {
    if (e.pointerType === 'mouse') setActiva(-1)
    arrastrando = false
  }

  root.addEventListener('pointermove', onMove)
  root.addEventListener('pointerdown', onDown)
  root.addEventListener('pointerup', onUp)
  root.addEventListener('pointercancel', onUp)
  root.addEventListener('pointerleave', onLeave)

  const ro = new ResizeObserver(ajustar)
  ro.observe(root)
  mq.addEventListener('change', montarVista)
  montarVista()

  return () => {
    token++
    ro.disconnect()
    mq.removeEventListener('change', montarVista)
    root.remove()
  }
}
