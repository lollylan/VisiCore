"""
PieksPlan - Export-Modul
PDF- und TXT-Export fuer Impfplaene pro Pflegeheim.
"""

import os
from datetime import datetime, date

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, PageBreak
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER


# Einverstaendnis-Labels fuer Export
EINVERSTAENDNIS_LABELS = {
    'NICHT_ANGEFRAGT': 'Noch nicht angefragt',
    'JA': 'Ja',
    'NEIN': 'Nein',
    'JA_JAEHRLICH': 'Ja (jaehrlich)',
    'JA_JAEHRLICH_NACHFRAGEN': 'Ja (jaehrl. nachfr.)',
}

STATUS_LABELS = {
    'OFFEN': 'Offen',
    'GEPLANT': 'Geplant',
    'DURCHGEFUEHRT': 'Durchgefuehrt',
}


def format_datum(datum_str):
    """Wandelt YYYY-MM-DD in DD.MM.YYYY um."""
    if not datum_str:
        return '-'
    try:
        d = datetime.strptime(str(datum_str), '%Y-%m-%d')
        return d.strftime('%d.%m.%Y')
    except (ValueError, TypeError):
        return str(datum_str)


def generate_pdf(data):
    """Generiert ein PDF fuer ein Pflegeheim."""
    tmp_dir = os.path.join(os.path.dirname(__file__), '.tmp')
    os.makedirs(tmp_dir, exist_ok=True)

    filename = f'impfplan_{data["pflegeheim"]["name"]}_{date.today().isoformat()}.pdf'
    pdf_path = os.path.join(tmp_dir, filename)

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=2 * cm,
        bottomMargin=1.5 * cm
    )

    styles = getSampleStyleSheet()

    # Eigene Styles
    title_style = ParagraphStyle(
        'PieksPlanTitle',
        parent=styles['Title'],
        fontSize=18,
        spaceAfter=4 * mm,
        textColor=colors.HexColor('#1a5276')
    )
    subtitle_style = ParagraphStyle(
        'PieksPlanSubtitle',
        parent=styles['Heading2'],
        fontSize=12,
        spaceAfter=2 * mm,
        textColor=colors.HexColor('#2c3e50')
    )
    wg_style = ParagraphStyle(
        'WGTitle',
        parent=styles['Heading3'],
        fontSize=11,
        spaceBefore=6 * mm,
        spaceAfter=3 * mm,
        textColor=colors.HexColor('#2980b9')
    )
    bewohner_style = ParagraphStyle(
        'BewohnerName',
        parent=styles['Normal'],
        fontSize=10,
        spaceBefore=4 * mm,
        spaceAfter=1 * mm,
        fontName='Helvetica-Bold'
    )
    info_style = ParagraphStyle(
        'Info',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#7f8c8d')
    )

    elements = []

    # Titel
    elements.append(Paragraph(
        f'Impfplan - {data["pflegeheim"]["name"]}', title_style
    ))
    elements.append(Paragraph(
        f'Export: {date.today().strftime("%d.%m.%Y")}', subtitle_style
    ))
    if data['pflegeheim'].get('adresse'):
        elements.append(Paragraph(
            f'Adresse: {data["pflegeheim"]["adresse"]}', info_style
        ))
    elements.append(Spacer(1, 6 * mm))

    # Pro Wohngruppe
    for wg_idx, wg in enumerate(data['wohngruppen']):
        if wg_idx > 0:
            elements.append(Spacer(1, 4 * mm))

        elements.append(Paragraph(
            f'Wohngruppe: {wg["name"]}', wg_style
        ))

        if not wg['bewohner']:
            elements.append(Paragraph(
                'Keine aktiven Bewohner.', info_style
            ))
            continue

        for bew in wg['bewohner']:
            # Bewohner-Name
            name_text = f'{bew["nachname"]}, {bew["vorname"]}'
            if bew.get('geburtsdatum'):
                name_text += f'  (Geb: {format_datum(bew["geburtsdatum"])})'
            elements.append(Paragraph(name_text, bewohner_style))

            if not bew.get('impfungen'):
                elements.append(Paragraph(
                    '  Keine Impfungen eingetragen.', info_style
                ))
                continue

            # Impfungs-Tabelle
            header = ['Impfung', 'Einverst.', 'Status',
                       'Geplant', 'Durchgef.', '\u2610']
            table_data = [header]

            for imp in bew['impfungen']:
                row = [
                    imp.get('impftyp', ''),
                    EINVERSTAENDNIS_LABELS.get(
                        imp.get('einverstaendnis_status', ''), '?'
                    ),
                    STATUS_LABELS.get(imp.get('status', ''), '?'),
                    format_datum(imp.get('plan_datum')),
                    format_datum(imp.get('durchfuehrung_datum')),
                    '\u2610'  # Checkbox-Zeichen
                ]
                table_data.append(row)

            col_widths = [100, 90, 80, 70, 70, 25]
            table = Table(table_data, colWidths=col_widths)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0),
                 colors.HexColor('#2c3e50')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (-1, 0), (-1, -1), 'CENTER'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
                ('TOPPADDING', (0, 1), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 2),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1),
                 [colors.white, colors.HexColor('#ecf0f1')]),
            ]))
            elements.append(table)

    doc.build(elements)
    return pdf_path


def generate_txt(data):
    """Generiert eine TXT-Datei fuer ein Pflegeheim."""
    tmp_dir = os.path.join(os.path.dirname(__file__), '.tmp')
    os.makedirs(tmp_dir, exist_ok=True)

    filename = f'impfplan_{data["pflegeheim"]["name"]}_{date.today().isoformat()}.txt'
    txt_path = os.path.join(tmp_dir, filename)

    lines = []
    lines.append('=' * 60)
    lines.append(f'IMPFPLAN - {data["pflegeheim"]["name"]}')
    lines.append(f'Export: {date.today().strftime("%d.%m.%Y")}')
    if data['pflegeheim'].get('adresse'):
        lines.append(f'Adresse: {data["pflegeheim"]["adresse"]}')
    lines.append('=' * 60)
    lines.append('')

    for wg in data['wohngruppen']:
        lines.append(f'--- Wohngruppe: {wg["name"]} ---')
        lines.append('')

        if not wg['bewohner']:
            lines.append('  Keine aktiven Bewohner.')
            lines.append('')
            continue

        for bew in wg['bewohner']:
            name_line = f'{bew["nachname"]}, {bew["vorname"]}'
            if bew.get('geburtsdatum'):
                name_line += f'  (Geb: {format_datum(bew["geburtsdatum"])})'
            lines.append(name_line)

            if not bew.get('impfungen'):
                lines.append('  Keine Impfungen eingetragen.')
            else:
                for imp in bew['impfungen']:
                    einv = EINVERSTAENDNIS_LABELS.get(
                        imp.get('einverstaendnis_status', ''), '?'
                    )
                    status = STATUS_LABELS.get(imp.get('status', ''), '?')

                    teile = [f'[ ] {imp.get("impftyp", "?")}']
                    teile.append(f'Einverst.: {einv}')
                    teile.append(f'Status: {status}')

                    if imp.get('plan_datum'):
                        teile.append(f'Geplant: {format_datum(imp["plan_datum"])}')
                    if imp.get('durchfuehrung_datum'):
                        teile.append(
                            f'Durchgef.: {format_datum(imp["durchfuehrung_datum"])}'
                        )

                    lines.append(f'  {" - ".join(teile)}')

            lines.append('')

    lines.append('=' * 60)
    lines.append('Ende des Impfplans')
    lines.append('=' * 60)

    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return txt_path
