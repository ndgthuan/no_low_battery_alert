"""Generate the opaque RGB app icon PNGs used by Resources/Info.plist.

Reads assets/icon_1024.png (the untouched source), flattens any transparency onto
pure black, resizes with Lanczos and writes RGB (no alpha) PNGs into Resources/.

Run from anywhere:  python scripts/make_icons.py
"""
import os

from PIL import Image

project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
source_path = os.path.join(project_dir, "assets", "icon_1024.png")
output_dir = os.path.join(project_dir, "Resources")

# file name -> edge length in pixels
icon_sizes = {
    "AppIcon60x60@2x.png": 120,
    "AppIcon60x60@3x.png": 180,
}

background_rgb = (0, 0, 0)


def flatten_on_black(source_image):
    """Return an opaque RGB image; transparent pixels become pure black."""
    rgba = source_image.convert("RGBA")
    backdrop = Image.new("RGBA", rgba.size, background_rgb + (255,))
    backdrop.alpha_composite(rgba)
    return backdrop.convert("RGB")


def make_icon(opaque_image, edge):
    """Lanczos-resize a square opaque RGB image to edge x edge."""
    return opaque_image.resize((edge, edge), Image.Resampling.LANCZOS)


def main():
    source_image = Image.open(source_path)
    opaque_image = flatten_on_black(source_image)
    os.makedirs(output_dir, exist_ok=True)
    for file_name, edge in icon_sizes.items():
        icon = make_icon(opaque_image, edge)
        output_path = os.path.join(output_dir, file_name)
        icon.save(output_path, format="PNG", optimize=True)
        print(f"wrote {output_path} {icon.size[0]}x{icon.size[1]} mode={icon.mode}")


if __name__ == "__main__":
    main()
