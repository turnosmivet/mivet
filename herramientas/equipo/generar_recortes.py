"""Genera los recortes de cada persona para la foto interactiva del equipo.

Uso:
    python generar_recortes.py FOTO_DESKTOP FOTO_MOBILE [--personas 4] [--salida ../../assets/equipo]

Produce, para cada variante (desktop / mobile):
    equipo-<variante>.webp           foto completa
    equipo-<variante>-<n>.webp       recorte con transparencia de la persona n (izq. a der.)
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
MAPA_PASO = 60


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
        alfa = cv2.GaussianBlur((m * 255).astype(np.uint8), (0, 0), 1.0)
        rgba = np.dstack([img, alfa])[y0:y1, x0:x1]
        Image.fromarray(rgba, "RGBA").save(f"{salida}/equipo-{variante}-{i + 1}.webp", quality=85, method=6)
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
        variantes[variante] = exportar(img, mascaras, variante, a.salida)
        print(f"{variante}: listo")
    print("\nPegá esto como VARIANTES en equipo-interactivo.js:\n")
    print(json.dumps(variantes, indent=2))


if __name__ == "__main__":
    main()
