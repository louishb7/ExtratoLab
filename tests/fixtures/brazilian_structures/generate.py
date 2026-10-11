"""Original fictitious recipes; observed concepts, never copied bank content."""
from pathlib import Path


def generate(path: Path, *, suffix: bool = True, count: int = 3,
             invalid_control: bool = False, hidden_tail: bool = False,
             omit_period: bool = False, bad_suffix: bool = False) -> None:
    from reportlab.pdfgen.canvas import Canvas
    c = Canvas(str(path), pagesize=(595, 842), invariant=1)
    c.setFont('Helvetica', 9)
    if not omit_period:
        c.drawString(30, 800, 'Extrato de 01/01/2029 até 31/01/2029')
    c.drawString(30, 777, 'Saldo inicial: R$ 100,00')
    final = 100 + (10 if count else 0) - (5 if count >= 2 else 0) + max(count - 2, 0)
    if invalid_control:
        final += 1
    c.drawString(30, 754, f'Saldo final: R$ {final},00')
    for i in range(count):
        if i and i % 20 == 0:
            c.showPage(); c.setFont('Helvetica', 9)
        y = 720 - (i % 20) * 28
        c.drawString(30, y, f'{min(2 + i, 31):02}/01')
        c.drawString(110, y, f'OPERACAO FICTICIA {i + 1}')
        magnitude, sign = ('10,00', '+') if i == 0 else ('5,00', '-') if i == 1 else ('1,00', '+')
        text = magnitude + sign if suffix else sign + magnitude
        if bad_suffix and i == 1:
            text += '-'
        c.drawRightString(450, y, text)
    if hidden_tail:
        c.drawString(30, y - 28, 'Observações:')
        c.drawString(30, y - 56, 'Valor adicional sem proprietário: 1,00')
    c.save()
