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

def process_images_to_canvas(images: List[Image.Image], boxes: List[Dict[str, float]], bg_color: str, canvas_w: int, canvas_h: int) -> Tuple[Image.Image, List[Dict[str, Any]]]:
    canvas = Image.new("RGBA", (canvas_w, canvas_h), hex_to_rgba(bg_color))
    placed_layers = []
    
    for _, (img, box) in enumerate(zip(images, boxes)):
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

def generate_psd_with_boxes(files: List[bytes], boxes: List[Dict[str, float]], width: int, height: int, bg_color: str, dpi: int) -> bytes:
    images = [Image.open(BytesIO(f)) for f in files]
    
    # 防止前端传过来的坐标越界或者不够图片数量
    used_boxes = boxes[:len(images)]
    
    canvas, placed_layers = process_images_to_canvas(images, used_boxes, bg_color, width, height)
    
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
    
    out_io = BytesIO()
    psd_data.write(out_io)
    return out_io.getvalue()
