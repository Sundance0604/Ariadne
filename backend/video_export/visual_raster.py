"""Rasterize the shared Canvas drawing plan without a browser or music runtime."""
from functools import lru_cache
import math

@lru_cache(maxsize=64)
def _font(path,size):
    from PIL import ImageFont
    return ImageFont.truetype(path,size)

@lru_cache(maxsize=2048)
def _text(path,size,text,color):
    from PIL import Image,ImageDraw
    f=_font(path,size);box=f.getbbox(text)
    im=Image.new('RGBA',(math.ceil(f.getlength(text))+3,box[3]-box[1]+3))
    ImageDraw.Draw(im).text((0,-box[1]),text,font=f,fill=color)
    return im

def raster(frame,font_path):
    from PIL import Image,ImageDraw,ImageColor
    image=Image.new('RGBA',(frame['width'],frame['height']))
    for c in frame['commands']:
        color=(*ImageColor.getrgb(c['color']),round(255*c['alpha']))
        if c['op']=='rect':
            x,y=round(c['x']),round(c['y']);w,h=round(c['x']+c['w'])-x,round(c['y']+c['h'])-y
            if w>0 and h>0:image.alpha_composite(Image.new('RGBA',(w,h),color),(x,y))
        elif c['op']=='line':
            x,y=round(min(c['x'],c['x2'])),round(min(c['y'],c['y2']))
            w,h=round(abs(c['x2']-c['x']))+1,round(abs(c['y2']-c['y']))+1
            small=Image.new('RGBA',(w,h));ImageDraw.Draw(small).line((c['x']-x,c['y']-y,c['x2']-x,c['y2']-y),fill=color,width=1)
            image.alpha_composite(small,(x,y))
        elif c['op']=='text':image.alpha_composite(_text(str(font_path),round(c['size']),c['text'],color),(round(c['x']),round(c['y'])))
    return image
