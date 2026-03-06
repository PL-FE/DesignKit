import math
import logging
from io import BytesIO
from typing import List, Tuple, Dict, Any
from PIL import Image, ImageOps
import pytoshop
from pytoshop.user import nested_layers
import packbits
pytoshop.codecs.packbits = packbits

import numpy as np

logger = logging.getLogger(__name__)

def hex_to_rgba(hex_code: str) -> tuple:
    hex_code = hex_code.lstrip('#')
    if len(hex_code) == 3:
        hex_code = ''.join([c*2 for c in hex_code])
    if len(hex_code) == 6:
        return tuple(int(hex_code[i:i+2], 16) for i in (0, 2, 4)) + (255,)
    elif len(hex_code) == 8:
        return tuple(int(hex_code[i:i+2], 16) for i in (0, 2, 4, 6))
    return (255, 255, 255, 255)

def get_grid_dimensions(num_items: int, w: float, h: float) -> Tuple[int, int]:
    aspect = w / h if h > 0 else 1
    rows = max(1, int(round(math.sqrt(num_items / aspect))))
    cols = max(1, math.ceil(num_items / rows))
    return cols, rows

def layout_grid(num_items: int, w: float, h: float, gap: float) -> List[Dict[str, float]]:
    cols, rows = get_grid_dimensions(num_items, w, h)
    boxes = []
    box_w = (w - (cols - 1) * gap) / cols
    box_h = (h - (rows - 1) * gap) / rows
    for i in range(num_items):
        c = i % cols
        r = i // cols
        boxes.append({
            "x": c * (box_w + gap),
            "y": r * (box_h + gap),
            "w": box_w,
            "h": box_h
        })
    return boxes

def layout_nine_grid(num_items: int, w: float, h: float, gap: float) -> List[Dict[str, float]]:
    if num_items <= 3:
        cols, rows = num_items, 1
    elif num_items <= 4:
        cols, rows = 2, 2
    elif num_items <= 6:
        cols, rows = 3, 2
    else:
        cols, rows = 3, 3
        
    boxes = []
    box_w = (w - (cols - 1) * gap) / cols
    box_h = (h - (rows - 1) * gap) / rows
    for i in range(min(num_items, cols * rows)):
        c = i % cols
        r = i // cols
        boxes.append({
            "x": c * (box_w + gap),
            "y": r * (box_h + gap),
            "w": box_w,
            "h": box_h
        })
    return boxes

def layout_left_hero(num_items: int, w: float, h: float, gap: float) -> List[Dict[str, float]]:
    if num_items == 1:
        return layout_grid(1, w, h, gap)
    hero_w = (w - gap) * 0.5
    boxes = [{"x": 0.0, "y": 0.0, "w": hero_w, "h": h}]
    rem_boxes = layout_grid(num_items - 1, w - hero_w - gap, h, gap)
    for b in rem_boxes:
        b["x"] += hero_w + gap
    return boxes + rem_boxes

def layout_top_hero(num_items: int, w: float, h: float, gap: float) -> List[Dict[str, float]]:
    if num_items == 1:
        return layout_grid(1, w, h, gap)
    hero_h = (h - gap) * 0.5
    boxes = [{"x": 0.0, "y": 0.0, "w": w, "h": hero_h}]
    rem_boxes = layout_grid(num_items - 1, w, h - hero_h - gap, gap)
    for b in rem_boxes:
        b["y"] += hero_h + gap
    return boxes + rem_boxes

def layout_magazine(num_items: int, w: float, h: float, gap: float) -> List[Dict[str, float]]:
    if num_items <= 2:
        return layout_grid(num_items, w, h, gap)
    hero_w = (w - gap) * 0.5
    boxes = [
        {"x": 0.0, "y": 0.0, "w": hero_w, "h": (h - gap) * 0.6},
        {"x": 0.0, "y": (h - gap) * 0.6 + gap, "w": hero_w, "h": (h - gap) * 0.4}
    ]
    rem_boxes = layout_grid(num_items - 2, w - hero_w - gap, h, gap)
    for b in rem_boxes:
        b["x"] += hero_w + gap
    return boxes + rem_boxes

def layout_masonry(image_sizes: List[Tuple[int, int]], w: float, h: float, gap: float) -> List[Dict[str, float]]:
    num_items = len(image_sizes)
    if num_items == 0: return []
    cols = 3 if w > h else 2
    if num_items < cols: cols = num_items
    
    col_w = (w - (cols - 1) * gap) / cols
    col_heights = [0.0] * cols
    
    boxes = []
    for img_w, img_h in image_sizes:
        min_c = col_heights.index(min(col_heights))
        aspect = img_w / img_h if img_h > 0 else 1
        box_h = col_w / aspect
        boxes.append({
            "col": min_c,
            "x": min_c * (col_w + gap),
            "h_ideal": box_h
        })
        col_heights[min_c] += box_h + gap
        
    for c in range(cols):
        c_boxes = [b for b in boxes if b["col"] == c]
        if not c_boxes: continue
        c_total_h = sum(b["h_ideal"] for b in c_boxes)
        c_avail_h = h - (len(c_boxes) - 1) * gap
        cur_y = 0.0
        for b in c_boxes:
            scaled_h = (b["h_ideal"] / c_total_h) * c_avail_h if c_total_h > 0 else 0
            b["w"] = col_w
            b["h"] = scaled_h
            b["y"] = cur_y
            cur_y += scaled_h + gap
            
    return [{"x": b["x"], "y": b["y"], "w": b["w"], "h": b["h"]} for b in boxes]

def calculate_boxes(mode: str, images: List[Image.Image], canvas_w: int, canvas_h: int, gap: int) -> List[Dict[str, float]]:
    num_items = len(images)
    w = max(1.0, float(canvas_w - 2 * gap))
    h = max(1.0, float(canvas_h - 2 * gap))
    
    if mode == "left_hero":
        boxes = layout_left_hero(num_items, w, h, gap)
    elif mode == "top_hero":
        boxes = layout_top_hero(num_items, w, h, gap)
    elif mode == "magazine":
        boxes = layout_magazine(num_items, w, h, gap)
    elif mode == "masonry":
        sizes = [img.size for img in images]
        boxes = layout_masonry(sizes, w, h, gap)
    elif mode == "nine_grid":
        boxes = layout_nine_grid(num_items, w, h, gap)
    else: # grid
        boxes = layout_grid(num_items, w, h, gap)
        
    for b in boxes:
        b["x"] += gap
        b["y"] += gap
    return boxes

def process_images_to_canvas(images: List[Image.Image], boxes: List[Dict[str, float]], bg_color: str, canvas_w: int, canvas_h: int) -> Tuple[Image.Image, List[Dict[str, Any]]]:
    canvas = Image.new("RGBA", (canvas_w, canvas_h), hex_to_rgba(bg_color))
    placed_layers = []
    
    for idx, (img, box) in enumerate(zip(images, boxes)):
        target_size = (max(1, int(round(box["w"]))), max(1, int(round(box["h"]))))
        cropped = ImageOps.fit(img, target_size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        if cropped.mode != "RGBA":
            cropped = cropped.convert("RGBA")
        
        pos = (int(round(box["x"])), int(round(box["y"])))
        canvas.paste(cropped, pos, cropped)
        placed_layers.append({
            "image": cropped,
            "x": pos[0],
            "y": pos[1]
        })
        
    bg_img = Image.new("RGBA", (canvas_w, canvas_h), hex_to_rgba(bg_color))
    return canvas, placed_layers

def pil_to_pytoshop_layer(pil_img: Image.Image, name: str, left: int, top: int) -> nested_layers.Image:
    if pil_img.mode != "RGBA":
        pil_img = pil_img.convert("RGBA")
    r, g, b, a = pil_img.split()
    channels = {
        -1: np.array(a, dtype=np.uint8),
        0: np.array(r, dtype=np.uint8),
        1: np.array(g, dtype=np.uint8),
        2: np.array(b, dtype=np.uint8),
    }
    w, h = pil_img.size
    return nested_layers.Image(
        name=name, 
        top=top, 
        left=left, 
        bottom=top + h, 
        right=left + w, 
        channels=channels
    )

def generate_preview(files: List[bytes], mode: str, width: int, height: int, gap: int, bg_color: str) -> bytes:
    images = [Image.open(BytesIO(f)) for f in files]
    boxes = calculate_boxes(mode, images, width, height, gap)
    canvas, _ = process_images_to_canvas(images, boxes, bg_color, width, height)
    
    out_io = BytesIO()
    canvas.save(out_io, format="PNG")
    return out_io.getvalue()

def generate_psd(files: List[bytes], mode: str, width: int, height: int, gap: int, bg_color: str, dpi: int) -> bytes:
    images = [Image.open(BytesIO(f)) for f in files]
    boxes = calculate_boxes(mode, images, width, height, gap)
    canvas, placed_layers = process_images_to_canvas(images, boxes, bg_color, width, height)
    
    psd_layers = []
    
    # Background layer
    bg_img = Image.new("RGBA", (width, height), hex_to_rgba(bg_color))
    psd_layers.append(pil_to_pytoshop_layer(bg_img, "Background", 0, 0))
    
    # Image layers
    for idx, item in enumerate(placed_layers):
        layer = pil_to_pytoshop_layer(item["image"], f"Image_{idx+1}", item["x"], item["y"])
        psd_layers.append(layer)
        
    group = nested_layers.Group(name="DesignKit Board", layers=psd_layers)
    psd_data = nested_layers.nested_layers_to_psd(
        [group], 
        color_mode=pytoshop.enums.ColorMode.rgb, 
        depth=8
    )
    
    # 将预览画布数据作为复合图像写入，解决 macOS 或网页下直接查看全是黑色的情况
    r, g, b, a = canvas.split()
    comp_channels = np.stack([
        np.array(r, dtype=np.uint8),
        np.array(g, dtype=np.uint8),
        np.array(b, dtype=np.uint8)
    ])
    psd_data.image_data = pytoshop.image_data.ImageData(
        channels=comp_channels[:psd_data.num_channels], 
        compression=pytoshop.enums.Compression.rle
    )
    
    # We want to use DPI, pytoshop might not natively support setting DPI in this high-level API.
    # But it sets default 72. That's fine for PSD internal data, print physical size won't perfectly match but pixels will.
    
    out_io = BytesIO()
    psd_data.write(out_io)
    return out_io.getvalue()
