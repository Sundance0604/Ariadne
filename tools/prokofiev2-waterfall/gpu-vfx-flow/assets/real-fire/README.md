The final render used three 96 fps motion-interpolated flame atlases made from
FX Elements **Fire Torch - 012**. The footage and derived PNG atlases remain
local. Obtain the source clip under its own terms, then run:

```sh
python3 build-real-fire-atlas.py FireTorch-012-ProRes.zip --ffmpeg ffmpeg
```

The build creates `flame-smooth-a.png`, `flame-smooth-b.png`, and
`flame-smooth-c.png` here. The builder also creates three lower-frame-rate
intermediate atlases, which may be removed after the smooth versions are
verified. The original model and video project do not need to be uploaded.
