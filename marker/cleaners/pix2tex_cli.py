from PIL import Image
from pix2tex.cli import LatexOCR

img = Image.open('/home/yejibing/code/marker/2.png')
model = LatexOCR()
print(model(img))