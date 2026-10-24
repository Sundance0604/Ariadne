"""Render score pages without requiring a system Poppler installation."""
from contextlib import closing
from pathlib import Path


def render_page(pdf_path, page_number, output, dpi=110):
    import pypdfium2 as pdfium

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    pending = output.with_suffix('.pending.png')
    try:
        with pdfium.PdfDocument(str(pdf_path)) as document:
            if not 1 <= page_number <= len(document):
                raise ValueError('PDF page is out of range')
            with closing(document[page_number - 1]) as page:
                with closing(page.render(scale=dpi / 72)) as bitmap:
                    with bitmap.to_pil() as picture:
                        picture.save(pending, format='PNG')
        pending.replace(output)
    finally:
        pending.unlink(missing_ok=True)
