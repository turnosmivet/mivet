# Foto interactiva del equipo

En la página **Conocer al equipo** (`/equipo`), al pasar el cursor sobre una persona (o al tocarla en el celular), su silueta se ilumina con un halo rosa, el resto de la foto se oscurece y aparece su nombre.

Esta guía explica cómo pasar ese cambio al **código fuente** del sitio (el proyecto React + Vite que tenés en la VM). En este repositorio solo está la versión compilada.

---

## Por qué hace falta

Este repositorio no tiene el código fuente, así que el cambio se hizo de dos formas:

1. **Archivos nuevos e independientes**, que se copian tal cual:
   - `assets/equipo/equipo-interactivo.js`: toda la lógica y los estilos del efecto, sin dependencias.
   - `assets/equipo/equipo-desktop*.webp|png` y `assets/equipo/equipo-mobile*.webp|png`: la foto, los recortes, las siluetas del halo (`*-halo.webp`) y los mapas.
2. **Una edición a mano del archivo compilado** `assets/index-B4mWpphv.js`, en la función de la página `/equipo`.

⚠️ La segunda parte **se pierde la próxima vez que compiles desde el código fuente**. Antes de volver a publicar algo desde la VM, aplicá los pasos de abajo. Si no, `/equipo` vuelve a mostrar la foto vieja sin efecto.

---

## Pasos en la VM

Los nombres de carpetas son los típicos de un proyecto Vite. Si los tuyos son distintos, adaptalos.

### 1. Traer los archivos de esta rama

En la carpeta de este repositorio (el que se publica en GitHub Pages):

```bash
git fetch origin
git checkout claude/magical-brown-dv9y5i   # o main, si ya se fusionó
```

### 2. Copiar imágenes y script a `public/`

Todo lo que está en `public/` se copia tal cual al compilar. Así quedan en `/mivet/assets/equipo/...`, igual que ahora:

```bash
# desde la carpeta del proyecto fuente
mkdir -p public/assets/equipo
cp RUTA/AL/REPO/mivet/assets/equipo/* public/assets/equipo/
```

Esto pisa `equipo-desktop.webp` y `equipo-mobile.webp`: la foto nueva reemplaza a la vieja (la de Majo y Sole de espaldas).

> Si en tu proyecto las imágenes de `/equipo` se importan desde `src/` en lugar de estar en `public/`, igual copiá **todo** a `public/assets/equipo/`. El script busca los archivos en `/mivet/assets/equipo/`.

### 3. Cambiar el componente de la página Equipo

Buscá el componente de la ruta `/equipo`. Es el que tiene el `<picture>` con `equipo-mobile.webp` / `equipo-desktop.webp` y el alt *"Majo y Sole, el equipo de MiVet, de espaldas…"*. Para encontrarlo:

```bash
grep -rn "equipo-desktop" src/
```

Hoy se ve más o menos así:

```jsx
<main className={styles.section}>
  <div className={styles.container}>
    <picture className={styles.media}>
      <source media="(max-width: 767px)" srcSet={`${BASE}assets/equipo/equipo-mobile.webp`} />
      <img src={`${BASE}assets/equipo/equipo-desktop.webp`} width={1376} height={768} alt="Majo y Sole…" … />
    </picture>
  </div>
</main>
```

Reemplazá el `<picture>…</picture>` por un `<div>` con `ref`, y agregá el `useEffect` que monta el efecto:

```jsx
import { useEffect, useRef } from 'react'
// …los imports que ya tenga el archivo (TopBar, WhatsApp, styles, etc.)

export default function Equipo() {
  const fotoRef = useRef(null)

  useEffect(() => {
    let cancelado = false
    let desmontar = null
    import(/* @vite-ignore */ `${import.meta.env.BASE_URL}assets/equipo/equipo-interactivo.js`)
      .then((mod) => {
        if (!cancelado) desmontar = mod.mount(fotoRef.current)
      })
    return () => {
      cancelado = true
      if (desmontar) desmontar()
    }
  }, [])

  return (
    <div className={styles.page}>
      {/* …barra superior igual que antes… */}
      <main className={styles.section}>
        <div className={styles.container}>
          <div ref={fotoRef} className={styles.media} />
        </div>
      </main>
      {/* …botón de WhatsApp igual que antes… */}
    </div>
  )
}
```

- `/* @vite-ignore */` le indica a Vite que no intente empaquetar ese archivo: se carga desde `public/` tal cual.
- `import.meta.env.BASE_URL` vale `/mivet/` si en `vite.config` tenés `base: '/mivet/'`, que es lo que usa el sitio hoy.
- El CSS de `.media` puede quedar como está. Las reglas `.media img {…}` ya no se usan, pero no molestan.

### 4. Probar en local

```bash
npm run dev
```

Abrí la URL que muestra la terminal (algo como `http://localhost:5173/mivet/`) y entrá a **Conocer al equipo**.

### 5. Compilar y publicar como siempre

```bash
npm run build
```

Después seguí tu proceso habitual, por ejemplo copiar `dist/` a este repositorio y hacer push a `main`. El nuevo `assets/index-XXXX.js` ya incluye el cambio, así que la edición a mano del bundle viejo deja de importar.

---

## Cambios frecuentes

Todo está en `public/assets/equipo/equipo-interactivo.js` (en este repositorio, `assets/equipo/equipo-interactivo.js`):

| Qué | Dónde |
|---|---|
| Nombres | `const NOMBRES = ['Sole', 'Rocío', 'Majo', 'Sabri']` (de izquierda a derecha) |
| Color e intensidad del halo | El `blur()` y los `rgba(255, …)` de `.eq-halo`, `.eq-nombre` y `@keyframes eq-latido` en el bloque `CSS` |
| Cuánto se oscurece el resto | `.eq-dim{… background:rgba(18,8,16,.6)}`: el último número va de 0 (nada) a 1 (negro) |
| Textos de ayuda | `'Tocá a cada una para conocerla'` / `'Pasá el cursor para conocer al equipo'` |
| Encuadre vertical de la foto | `const POS_Y = 0.7` (0 = arriba, 1 = abajo) |
| Cuánto se recorta a los costados en celular | `const RECORTE_LATERAL_MAX = 0.05` (5% por lado) |

## Si cambian las fotos o el equipo

Los recortes se generan automáticamente con `generar_recortes.py`, en esta misma carpeta. Necesitás Python 3.10 o más nuevo:

```bash
cd herramientas/equipo
python3 -m venv venv && source venv/bin/activate   # en Windows: venv\Scripts\activate
pip install -r requirements.txt
python generar_recortes.py FOTO_HORIZONTAL.jpg FOTO_VERTICAL.jpg --personas 4
```

- La primera vez descarga los modelos (unos 300 MB) y tarda unos minutos.
- Escribe los archivos en `assets/equipo/` y al final imprime un bloque JSON. Pegalo en lugar del `const VARIANTES = {…}` de `equipo-interactivo.js` (las claves coinciden).
- Si cambia la cantidad de personas, usá `--personas N` y ajustá `NOMBRES`.
- Mirá el resultado en el navegador. Donde dos personas se superponen (manos en hombros, pelo encima), el recorte automático puede asignar un pedacito a la persona equivocada.

## Cómo funciona por dentro

- La foto completa se muestra normal. Encima hay, por persona, dos capas: el halo (`.eq-halo`, que usa `equipo-*-N-halo.webp`: una silueta suavizada de color liso con el brillo rosa) y la figura nítida arriba (`.eq-figura`, el recorte exacto). En Rocío, Majo y Sabri el halo se omite en el lado izquierdo del cuerpo (se apoyan en la persona de al lado): queda la cabeza y el lado derecho, y se desvanece desde el cuello hacia abajo. Sole conserva el contorno completo, salvo un tramo del brazo izquierdo donde se usa el recorte original (`RESTAURAR_ORIGINAL` en `generar_recortes.py`: cajas donde el refinado empeora el borde). El borde izquierdo del pelo de Sabri (desktop) se endereza con una curva y transparencia subpíxel (`RECTIFICAR_BORDE`), porque en la foto ondula ~1 px y se veía como serrucho. La línea de corte del lado izquierdo se suaviza como curva (`HALO_CORTE_SIGMA`) para que no copie los dientes del pelo. El halo usa su propia silueta suavizada para que el contorno no ondule con los detalles del recorte (pelo, mangas); si la regenerás, los parámetros están al inicio de `generar_recortes.py` (`HALO_SIGMA`, `HALO_UMBRAL`, `HALO_TOPE`, `HALO_INSET`). Entre la foto y los recortes hay una capa oscura (`.eq-dim`).
- Para saber qué persona está bajo el cursor se usa el **mapa** (`*-mapa.png`): una imagen chiquita donde cada píxel tiene el número de la persona (gris 60 = 1, 120 = 2, etc.). Por eso el efecto se activa solo sobre la silueta y no sobre el rectángulo del recorte.
- El efecto se habilita recién cuando todas las imágenes terminaron de cargar, para que nunca se dibuje sobre un recorte a medio cargar.
- En pantallas de hasta 767 px de ancho se usa la foto vertical. Si se gira el celular o cambia el tamaño de la ventana, cambia de foto sola.
- Con teclado (Tab) se recorre a cada persona, y los lectores de pantalla leen los nombres.
