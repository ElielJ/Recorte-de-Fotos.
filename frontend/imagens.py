"""Conversões entre arrays NumPy e imagens do Qt."""
import cv2
import numpy as np
from PySide6.QtGui import QImage, QPixmap

from backend.recorte import para_8bits


def pixmap_de_array(img):
    img = np.ascontiguousarray(para_8bits(img))
    alt, larg = img.shape[:2]
    if img.ndim == 2:
        q = QImage(img.data, larg, alt, larg, QImage.Format_Grayscale8)
    else:
        q = QImage(img.data, larg, alt, 3 * larg, QImage.Format_RGB888)
    return QPixmap.fromImage(q.copy())


def pixmap_da_previa(foto):
    img = cv2.imdecode(np.frombuffer(foto.previa, np.uint8), cv2.IMREAD_UNCHANGED)
    if img.ndim == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return pixmap_de_array(np.rot90(img, -foto.rot90))
