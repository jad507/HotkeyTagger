# save_digits_flat.py
import os
from pathlib import Path
from sklearn import datasets
from sklearn.datasets import fetch_olivetti_faces
from PIL import Image
import numpy as np


def digitDL():
    OUTPUT_DIR = Path("digits_images_flat")
    UPSCALE_TO = None  # e.g., 32, or None
    digits = datasets.load_digits()
    images = digits.images
    labels = digits.target

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for idx, (img, label) in enumerate(zip(images, labels)):
        img_u8 = (img / 16.0 * 255).astype(np.uint8)
        pil_img = Image.fromarray(img_u8, mode="L")

        if UPSCALE_TO is not None and UPSCALE_TO != img_u8.shape[0]:
            pil_img = pil_img.resize((UPSCALE_TO, UPSCALE_TO), resample=Image.NEAREST)

        out_path = OUTPUT_DIR / f"{label}_digit_{idx:04d}.png"
        pil_img.save(out_path)

    print(f"Saved {len(images)} images to: {OUTPUT_DIR.resolve()}")


def olivettiDL():
    OUTPUT_DIR = Path("olivetti_faces_flat")
    UPSCALE_TO = None  # e.g., 128 or None
    SAVE_RGB = False
    FILE_EXT = "png"
    faces = fetch_olivetti_faces(shuffle=False)
    images = faces.images
    targets = faces.target

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for idx, (img, subj) in enumerate(zip(images, targets)):
        img_u8 = (img * 255).clip(0, 255).astype(np.uint8)
        pil_img = Image.fromarray(img_u8, mode="L")

        if UPSCALE_TO is not None and UPSCALE_TO != img_u8.shape[0]:
            pil_img = pil_img.resize((UPSCALE_TO, UPSCALE_TO), resample=Image.BILINEAR)

        if SAVE_RGB:
            pil_img = pil_img.convert("RGB")

        out_path = OUTPUT_DIR / f"s{int(subj):02d}_img_{idx:03d}.{FILE_EXT}"
        pil_img.save(out_path)

    print(f"Saved {len(images)} images to: {OUTPUT_DIR.resolve()}")

if __name__ == "__main__":
    digitDL()
    olivettiDL()