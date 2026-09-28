import shutil
import tempfile
import unittest
from pathlib import Path

from portuguese_pipeline.extract import extract_pdf, reading_order_options


@unittest.skipUnless(shutil.which('pdftotext'), 'Poppler is required for PDF integration')
class PdfReadingOrderTests(unittest.TestCase):
    def test_two_columns_are_read_sequentially_without_losing_lines(self):
        left = [f'Left narrative sentence number {i:02d}.' for i in range(12)]
        right = [f'Right independent statement {i:02d}.' for i in range(12)]
        if reading_order_options():
            left[3] = 'Literal URL https://example.org/gestao-de-'
            left[4] = 'pessoas must keep its line-end hyphen.'
        stream = '\n'.join(
            f'BT /F1 10 Tf 1 0 0 1 {x} {740-i*15} Tm ({line}) Tj ET'
            for x, lines in [(40, left), (340, right)]
            for i, line in enumerate(lines)
        ).encode()
        objects = [
            b'<< /Type /Catalog /Pages 2 0 R >>',
            b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
            b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
            b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
            f'<< /Length {len(stream)} >>\nstream\n'.encode() + stream + b'\nendstream',
        ]
        data = bytearray(b'%PDF-1.4\n')
        offsets = [0]
        for i, obj in enumerate(objects, 1):
            offsets.append(len(data))
            data.extend(f'{i} 0 obj\n'.encode() + obj + b'\nendobj\n')
        xref = len(data)
        data.extend(b'xref\n0 6\n0000000000 65535 f \n')
        for offset in offsets[1:]:
            data.extend(f'{offset:010d} 00000 n \n'.encode())
        data.extend(f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'columns.pdf'
            path.write_bytes(data)
            result = extract_pdf(path, work_dir=Path(directory), workers=1, dpi=300, embedded_word_floor=1)
        text = result.units[0].text
        for line in left + right:
            self.assertEqual(text.count(line), 1)
        self.assertLess(text.index(left[-1]), text.index(right[0]))
        self.assertEqual(result.tools['text_order'], 'reading')
