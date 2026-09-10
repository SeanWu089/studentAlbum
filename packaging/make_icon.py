#!/usr/bin/env python3
"""Create the Student Album app icon as PNG and a multi-size Windows ICO."""
from pathlib import Path
from PIL import Image, ImageDraw


OUT = Path(__file__).resolve().parent / 'assets'
SIZE = 1024


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    image = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((48, 48, 976, 976), radius=224, fill='#2E6F5E')
    draw.rounded_rectangle((186, 190, 838, 846), radius=112, fill='#F7F4EC')
    draw.rounded_rectangle((232, 244, 792, 792), radius=74, fill='#FFFFFF')
    draw.ellipse((330, 300, 694, 664), fill='#DCEBE4')
    draw.ellipse((424, 362, 600, 538), fill='#2E6F5E')
    draw.rounded_rectangle((350, 536, 674, 688), radius=76, fill='#2E6F5E')
    draw.rounded_rectangle((428, 748, 596, 780), radius=16, fill='#D0DED7')
    png = OUT / 'student-album.png'
    ico = OUT / 'student-album.ico'
    image.save(png, optimize=True)
    image.save(ico, format='ICO', sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(png)
    print(ico)


if __name__ == '__main__':
    main()
