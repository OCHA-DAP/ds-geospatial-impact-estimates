"""Inline the four data .js files into index.html -> bundle.html (the file that gets encrypted)."""
import pathlib, re
HERE = pathlib.Path(__file__).parent
t = (HERE / "index.html").read_text()
for name in ("data.js", "extents.js", "hexes.js", "asdel.js"):
    tag = f'<script src="{name}"></script>'
    if t.count(tag) != 1:
        raise SystemExit(f"expected one {tag}, found {t.count(tag)}")
    js = (HERE / name).read_text()
    if not js.strip():
        raise SystemExit(f"{name} is empty; run the exporter first")
    t = t.replace(tag, "<script>\n" + js + "\n</script>")
(HERE / "bundle.html").write_text(t)
print(f"bundle.html: {len(t) / 1e6:.1f} MB")
