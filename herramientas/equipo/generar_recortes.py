"""Genera los recortes de cada persona para la foto interactiva del equipo.

Uso:
    python generar_recortes.py FOTO_DESKTOP FOTO_MOBILE [--personas 4] [--salida ../../assets/equipo]

Produce, para cada variante (desktop / mobile):
    equipo-<variante>.webp           foto completa
    equipo-<variante>-<n>.webp       recorte con transparencia de la persona n (izq. a der.)
    equipo-<variante>-<n>-halo.webp  silueta suavizada y de color liso, solo para dibujar el halo
    equipo-<variante>-mapa.png       mapa a 1/4 de resolución (gris = n * 60) para saber
                                     qué persona está bajo el cursor
e imprime el bloque VARIANTES para pegar en equipo-interactivo.js.

Cómo funciona: YOLO detecta a las personas y SAM 2 recorta cada una con precisión,
usando la caja de YOLO más puntos positivos (la propia persona) y negativos (las demás).
Los modelos (~300 MB) se descargan solos la primera vez.
"""
import argparse
import json

import cv2
import numpy as np
from PIL import Image
from ultralytics import SAM, YOLO

MAPA_ESCALA = 4
SUAVIZADO_BORDE = 4  # px de arco para promediar el contorno del recorte (0 = sin suavizar)
MAPA_PASO = 60
# El halo se dibuja con una silueta aparte, suavizada, para que el contorno no ondule con los
# detalles del recorte (pelo, mangas). Se desenfoca la máscara (HALO_SIGMA px, en una foto de
# 2000 px de ancho) y se vuelve a binarizar con un umbral bajo (HALO_UMBRAL), que la agranda un
# par de px: así nunca deja pelo o ropa fuera del halo. La silueta no puede crecer más de
# HALO_TOPE px, para no rellenar con rosa liso los huecos entre dos personas. Además, todas
# menos la primera se apoyan en la persona de su izquierda: ahí el halo se omite en el cuerpo
# (queda la cabeza y el lado derecho) y se desvanece de a poco desde el cuello hacia abajo.
# En mobile la foto se ve más chica, así que las medidas en px se multiplican por ESCALA_HALO.
HALO_SIGMA = 10
HALO_UMBRAL = 0.38
HALO_TOPE = 8
HALO_CABEZA = 0.30   # alto de la cabeza (con el pelo), como fracción del alto de la persona
HALO_RAMPA = 0.12    # tramo (fracción del alto) en que el lado izquierdo se va apagando
HALO_INSET = 70      # px que se recorta del borde izquierdo del cuerpo, al final de la rampa
HALO_CORTE_SIGMA = 35  # px de suavizado vertical de la línea de corte (más = baja más lisa)
ESCALA_HALO = {"desktop": 1.0, "mobile": 1.4}
HALO_COLOR = (255, 150, 205)


def silueta_halo(m, variante, sin_lado_izq=False):
    """m: máscara 0/1 del recorte -> RGBA liso con el contorno suavizado."""
    f = ESCALA_HALO.get(variante, 1.0)
    sigma = HALO_SIGMA * f
    pad = int(sigma * 4)
    g = cv2.GaussianBlur(np.pad(m.astype(np.float32), pad), (0, 0), sigma)
    s = (g > HALO_UMBRAL).astype(np.uint8)[pad:-pad, pad:-pad]
    tope = int(round(HALO_TOPE * f))
    s &= cv2.dilate(m.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * tope + 1, 2 * tope + 1)))
    if sin_lado_izq:
        ys, xs = np.where(s > 0)
        arriba, abajo = ys.min(), ys.max()
        alto = abajo - arriba
        corte, rampa = arriba + HALO_CABEZA * alto, max(1.0, HALO_RAMPA * alto)
        filas = np.arange(arriba, abajo + 1)
        borde = np.array([np.flatnonzero(s[y])[0] if s[y].any() else np.nan for y in filas], np.float32)
        borde = np.where(np.isnan(borde), np.nanmean(borde), borde)
        # el corte es el borde izquierdo corrido hacia adentro (de a poco desde el cuello); se lo
        # suaviza como curva para que no copie los dientes del pelo y baje liso
        corrido = borde + HALO_INSET * f * np.clip((filas - corte) / rampa, 0, 1)
        sg = HALO_CORTE_SIGMA * f
        r = int(sg * 3)
        k = np.exp(-0.5 * (np.arange(-r, r + 1) / sg) ** 2)
        k /= k.sum()
        liso = np.convolve(np.pad(corrido, r, mode="edge"), k, "valid")
        for y, x in zip(filas, np.maximum(liso, borde)):
            s[y, : int(round(x))] = 0
        s = (cv2.GaussianBlur(s.astype(np.float32), (0, 0), 2.0) > 0.5).astype(np.uint8)
    alfa = cv2.GaussianBlur(s * 255, (0, 0), 1.0)
    rgb = np.empty(m.shape + (3,), np.uint8)
    rgb[:] = HALO_COLOR
    return np.dstack([rgb, alfa])


def _el(n):
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * n + 1, 2 * n + 1))


def _suavizar_contorno(m, sigma):
    """Promedia el contorno (externo y de huecos) a lo largo del borde: quita escalones y
    ondas chicas sin mover el borde más de ~1 px, porque ya está sobre el borde real."""
    pad = 4 * int(sigma) + 4
    mm = np.pad(m.astype(np.uint8), pad)
    cs, jer = cv2.findContours(mm, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    r = int(sigma * 3)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    minimo = 0.001 * mm.sum()
    out = np.zeros_like(mm)
    for c, h in zip(cs, jer[0]):
        if abs(cv2.contourArea(c)) < minimo:
            continue
        c = c[:, 0, :].astype(np.float32)
        if len(c) > 2 * r + 1:
            e = np.pad(c, ((r, r), (0, 0)), mode="wrap")
            c = np.stack([np.convolve(e[:, 0], k, "valid"), np.convolve(e[:, 1], k, "valid")], 1)
        cv2.fillPoly(out, [np.round(c).astype(np.int32)], 0 if h[3] >= 0 else 1)
    return out[pad:-pad, pad:-pad]


def refinar(img, mascaras, banda=9, iters=6):
    """SAM predice la máscara a baja resolución y la agranda: el borde queda impreciso (corta pelo,
    hace bucles en las manos) y se nota como serrucho. Acá se ajusta a los bordes reales de la foto
    con GrabCut, solo dentro de una franja de `banda` px, y respetando el corte entre personas."""
    H, W = img.shape[:2]
    bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    salida = []
    for i, m in enumerate(mascaras):
        m = m.astype(np.uint8)
        ys, xs = np.where(m > 0)
        p = banda + 12
        x0, x1 = max(0, xs.min() - p), min(W, xs.max() + 1 + p)
        y0, y1 = max(0, ys.min() - p), min(H, ys.max() + 1 + p)
        mc = m[y0:y1, x0:x1]
        otras = np.zeros_like(mc)
        for j, o in enumerate(mascaras):
            if j != i: otras |= o[y0:y1, x0:x1].astype(np.uint8)
        otras = cv2.dilate(otras,  _el(4))
        gc = np.full(mc.shape, cv2.GC_PR_BGD, np.uint8)
        gc[mc > 0] = cv2.GC_PR_FGD
        gc[cv2.erode(mc,  _el(banda)) > 0] = cv2.GC_FGD
        gc[cv2.dilate(mc,  _el(banda)) == 0] = cv2.GC_BGD
        # donde hay otra persona pegada, se respeta el corte original
        gc[(otras > 0) & (mc > 0)] = cv2.GC_FGD
        gc[(otras > 0) & (mc == 0)] = cv2.GC_BGD
        bg = np.zeros((1, 65)); fg = np.zeros((1, 65))
        cv2.grabCut(bgr[y0:y1, x0:x1], gc, None, bg, fg, iters, cv2.GC_INIT_WITH_MASK)
        r = ((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD)).astype(np.uint8)
        r = _suavizar_contorno(r, SUAVIZADO_BORDE)
        full = np.zeros((H, W), np.uint8); full[y0:y1, x0:x1] = r
        salida.append(full)
    return salida


# Tramos donde el refinado empeora el recorte (GrabCut se confunde cuando dos zonas contiguas
# tienen colores parecidos) y conviene quedarse con el recorte original del modelo. Se declaran
# como variante -> persona (0 = la primera de la izquierda) -> lista de cajas
# (x0, y0, x1, y1, en px de la foto). Fuera de la caja no cambia nada.
# Sole (desktop): debajo de la manga izquierda el refinado metía una "panza" hacia adentro.
RESTAURAR_ORIGINAL = {
    "desktop": {0: [(395, 845, 485, 945)]},
}


def restaurar_original(refinadas, originales, variante):
    salida = [m.copy() for m in refinadas]
    for i, cajas in RESTAURAR_ORIGINAL.get(variante, {}).items():
        for x0, y0, x1, y1 in cajas:
            salida[i][y0:y1, x0:x1] = originales[i][y0:y1, x0:x1]
        salida[i] = _suavizar_contorno(salida[i], SUAVIZADO_BORDE)  # une el tramo con el resto
    return salida


def segmentar(ruta, n_personas, yolo, sam):
    img = Image.open(ruta).convert("RGB")
    W, H = img.size
    r = yolo(ruta, classes=[0], conf=0.25, verbose=False)[0]
    cajas = r.boxes.xyxy.cpu().numpy()
    # Descarta personas chicas del fondo (ej. gente en la calle) y se queda con las más grandes.
    cajas = cajas[(cajas[:, 3] - cajas[:, 1]) > 0.3 * H]
    cajas = cajas[np.argsort(-(cajas[:, 3] - cajas[:, 1]))][:n_personas]
    cajas = cajas[np.argsort(cajas[:, 0])]
    if len(cajas) != n_personas:
        raise SystemExit(f"{ruta}: se detectaron {len(cajas)} personas, se esperaban {n_personas}")

    mascaras = []
    for i, b in enumerate(cajas):
        cx = (b[0] + b[2]) / 2
        alto = b[3] - b[1]
        pts = [[cx, b[1] + 0.15 * alto], [cx, b[1] + 0.45 * alto]]
        lbl = [1, 1]
        for j, o in enumerate(cajas):
            if j != i:
                pts.append([(o[0] + o[2]) / 2, o[1] + 0.3 * (o[3] - o[1])])
                lbl.append(0)
        res = sam(ruta, bboxes=[b.tolist()], points=[pts], labels=[lbl], verbose=False)[0]
        mascaras.append(res.masks.data.cpu().numpy()[0] > 0.5)
    return np.array(img), mascaras


def limpiar(m, W, H):
    m = m.astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    grande = 1 + np.argmax(st[1:, cv2.CC_STAT_AREA])
    out = np.zeros_like(m)
    for i in range(1, n):
        if i == grande or st[i, cv2.CC_STAT_AREA] > 0.01 * st[grande, cv2.CC_STAT_AREA]:
            out[lab == i] = 1
    # Rellena agujeros chicos internos.
    inv = (1 - out).astype(np.uint8)
    n2, l2, s2, _ = cv2.connectedComponentsWithStats(inv, 4)
    for i in range(1, n2):
        x, y, w, h, a = s2[i]
        if a < 0.002 * out.sum() and x > 0 and y > 0 and x + w < W and y + h < H:
            out[l2 == i] = 1
    return cv2.morphologyEx(out, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))


# Tramos de borde casi vertical (pelo lacio) que en la foto ondulan ~1 px y se ven como serrucho.
# Se ajusta una curva suave (polinomio de grado 3) al borde izquierdo y se dibuja la transparencia
# con cobertura fraccional de píxel (subpíxel), así no queda escalera. Se mezcla con el borde
# real en los extremos del tramo para que no haya un escalón. Cambia solo la transparencia, no la
# máscara. variante -> persona (0 = la primera de la izquierda) -> lista de (y0, y1), en px.
# Sabri (desktop): el borde izquierdo del pelo debe bajar liso.
RECTIFICAR_BORDE = {
    "desktop": {3: [(440, 585)]},
}
RECTIFICAR_TRANSICION = 24


def rectificar_borde(alfa, variante, i):
    alfa = alfa.copy()
    for y0, y1 in RECTIFICAR_BORDE.get(variante, {}).get(i, []):
        ys = np.arange(y0, y1)
        xold = []
        for y in ys:
            xi = int(np.flatnonzero(alfa[y] > 127)[0])
            seg = alfa[y, xi - 4 : xi + 5] / 255.0
            xold.append(xi - 4 + (9 - seg.sum()))
        xold = np.array(xold)
        xfit = np.polyval(np.polyfit(ys, xold, 3), ys)
        w = np.clip(np.minimum(ys - y0, y1 - 1 - ys) / RECTIFICAR_TRANSICION, 0, 1)
        w = w * w * (3 - 2 * w)
        xnew = xold + w * (xfit - xold)
        for y, x in zip(ys, xnew):
            cols = np.arange(int(x) - 4, int(x) + 5)
            alfa[y, cols] = (np.clip(cols + 1 - x, 0, 1) * 255).astype(alfa.dtype)
    return alfa


def exportar(img, mascaras, variante, salida):
    H, W = img.shape[:2]
    mascaras = [limpiar(m, W, H) for m in mascaras]
    lab = np.zeros((H, W), np.uint8)
    for i, m in enumerate(mascaras):
        lab[m > 0] = i + 1
    chico = cv2.resize(lab, (W // MAPA_ESCALA, H // MAPA_ESCALA), interpolation=cv2.INTER_NEAREST)
    Image.fromarray(chico * MAPA_PASO).convert("L").save(f"{salida}/equipo-{variante}-mapa.png", optimize=True)
    Image.fromarray(img).save(f"{salida}/equipo-{variante}.webp", quality=82, method=6)

    personas = []
    for i, m in enumerate(mascaras):
        ys, xs = np.where(m > 0)
        pad = 4
        x0, y0 = max(0, xs.min() - pad), max(0, ys.min() - pad)
        x1, y1 = min(W, xs.max() + 1 + pad), min(H, ys.max() + 1 + pad)
        alfa = rectificar_borde(cv2.GaussianBlur((m * 255).astype(np.uint8), (0, 0), 1.0), variante, i)
        rgba = np.dstack([img, alfa])[y0:y1, x0:x1]
        Image.fromarray(rgba, "RGBA").save(f"{salida}/equipo-{variante}-{i + 1}.webp", quality=85, method=6)
        halo = silueta_halo(m, variante, i > 0)[y0:y1, x0:x1]
        Image.fromarray(halo, "RGBA").save(f"{salida}/equipo-{variante}-{i + 1}-halo.webp", quality=80, method=6)
        arriba = ys.min()
        cx = int(xs[ys < arriba + 40].mean())
        personas.append(dict(
            x=round(x0 / W * 100, 3), y=round(y0 / H * 100, 3),
            w=round((x1 - x0) / W * 100, 3), h=round((y1 - y0) / H * 100, 3),
            hx=round(cx / W * 100, 2), hy=round(arriba / H * 100, 2),
        ))
    return dict(w=W, h=H, personas=personas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("desktop")
    ap.add_argument("mobile")
    ap.add_argument("--personas", type=int, default=4)
    ap.add_argument("--salida", default="../../assets/equipo")
    a = ap.parse_args()
    yolo, sam = YOLO("yolo11x-seg.pt"), SAM("sam2.1_l.pt")
    variantes = {}
    for variante, ruta in [("desktop", a.desktop), ("mobile", a.mobile)]:
        img, mascaras = segmentar(ruta, a.personas, yolo, sam)
        originales = mascaras
        mascaras = restaurar_original(refinar(img, mascaras), originales, variante)
        variantes[variante] = exportar(img, mascaras, variante, a.salida)
        print(f"{variante}: listo")
    print("\nPegá esto como VARIANTES en equipo-interactivo.js:\n")
    print(json.dumps(variantes, indent=2))


if __name__ == "__main__":
    main()
