"""
VisiCore - Export-Modul
PDF-Export fuer Einrichtungen und Tagesrouten.
"""

import os
from datetime import datetime, date
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT


# Status-Labels fuer Anzeige
EINVERSTAENDNIS_LABELS = {
    'NICHT_ANGEFRAGT': 'Nicht angefragt',
    'JA': 'Ja',
    'NEIN': 'Nein',
    'JA_JAEHRLICH': 'Ja (jaehrlich)',
    'JA_JAEHRLICH_NACHFRAGEN': 'Ja (jaehrl. nachfr.)',
    'NEIN_JAEHRLICH_NACHFRAGEN': 'Nein (jaehrl. nachfr.)',
}

STATUS_LABELS = {
    'OFFEN': 'Offen',
    'GEPLANT': 'Geplant',
    'DURCHGEFUEHRT': 'Durchgefuehrt',
}


def format_datum(datum_str):
    """Wandelt YYYY-MM-DD in DD.MM.YYYY um."""
    if not datum_str:
        return ''
    try:
        if isinstance(datum_str, str):
            d = datetime.strptime(datum_str[:10], '%Y-%m-%d')
        elif isinstance(datum_str, (date, datetime)):
            d = datum_str
        else:
            return str(datum_str)
        return d.strftime('%d.%m.%Y')
    except (ValueError, TypeError):
        return str(datum_str)


def generate_einrichtung_pdf(data):
    """
    Generiert ein PDF fuer eine Einrichtung mit allen Stationen und Patienten.
    data: Dict von database.get_export_data()
    Gibt: BytesIO-Objekt mit dem PDF zurueck.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)

    styles = getSampleStyleSheet()

    # Custom Styles
    title_style = ParagraphStyle('TitleCustom', parent=styles['Title'],
                                  fontSize=16, spaceAfter=6*mm)
    subtitle_style = ParagraphStyle('SubTitle', parent=styles['Heading2'],
                                     fontSize=13, spaceAfter=4*mm,
                                     textColor=colors.HexColor('#333333'))
    info_style = ParagraphStyle('Info', parent=styles['Normal'],
                                 fontSize=9, textColor=colors.HexColor('#555555'))
    header_style = ParagraphStyle('Header', parent=styles['Normal'],
                                   fontSize=8, textColor=colors.white,
                                   alignment=TA_CENTER)
    cell_style = ParagraphStyle('Cell', parent=styles['Normal'],
                                 fontSize=8)
    cave_style = ParagraphStyle('Cave', parent=styles['Normal'],
                                 fontSize=8, textColor=colors.HexColor('#cc0000'))

    elements = []
    einrichtung = data['einrichtung']

    # Titel
    elements.append(Paragraph(f"Einrichtung: {einrichtung['name']}", title_style))
    elements.append(Paragraph(
        f"Adresse: {einrichtung.get('adresse', '–')} | "
        f"Stand: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        info_style
    ))
    elements.append(Spacer(1, 8*mm))

    for station_data in data['stationen']:
        station = station_data['station']
        patienten = station_data['patienten']

        elements.append(Paragraph(
            f"Station: {station['name']} "
            f"(Intervall: {station.get('intervall_tage', '–')} Tage)",
            subtitle_style
        ))

        if not patienten:
            elements.append(Paragraph("Keine Patienten in dieser Station.", info_style))
            elements.append(Spacer(1, 6*mm))
            continue

        # Tabelle: Name | Geb. | CAVE | Impfungen | Notizen
        header = ['Name', 'Geb.-Datum', 'CAVE', 'Impfungen', 'Notizen']
        table_data = [header]

        for pat_data in patienten:
            patient = pat_data['patient']
            impfungen = pat_data['impfungen']

            # Impfungen formatieren
            impf_texte = []
            for imp in impfungen:
                status = STATUS_LABELS.get(imp.get('status', ''), imp.get('status', ''))
                ev = EINVERSTAENDNIS_LABELS.get(
                    imp.get('einverstaendnis_status', ''),
                    imp.get('einverstaendnis_status', '')
                )
                impf_texte.append(f"{imp['impftyp']}: {status} (EV: {ev})")
            impf_str = '\n'.join(impf_texte) if impf_texte else '–'

            row = [
                Paragraph(f"{patient['nachname']}, {patient['vorname']}", cell_style),
                Paragraph(format_datum(patient.get('geburtsdatum')), cell_style),
                Paragraph(patient.get('cave', '') or '–', cave_style),
                Paragraph(impf_str.replace('\n', '<br/>'), cell_style),
                Paragraph(patient.get('notizen', '') or '–', cell_style),
            ]
            table_data.append(row)

        # Tabelle erstellen
        col_widths = [3.5*cm, 2.2*cm, 3*cm, 5*cm, 4*cm]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2d3050')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            # Zeilen
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 8*mm))

    doc.build(elements)
    buffer.seek(0)
    return buffer


def generate_station_liste_pdf(station, patienten):
    """
    Generiert ein PDF fuer die Kompaktuebersicht einer Station.
    station: Dict mit Stationsdaten (name, einrichtung_name, etc.)
    patienten: Liste der Patienten in der Station.
    Gibt: BytesIO-Objekt mit dem PDF zurueck.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleCustom', parent=styles['Title'],
                                  fontSize=16, spaceAfter=6*mm)
    info_style = ParagraphStyle('Info', parent=styles['Normal'],
                                 fontSize=9, textColor=colors.HexColor('#555555'))
    cell_style = ParagraphStyle('Cell', parent=styles['Normal'], fontSize=8)
    cave_style = ParagraphStyle('Cave', parent=styles['Normal'],
                                 fontSize=8, textColor=colors.HexColor('#cc0000'))

    elements = []

    elements.append(Paragraph(
        f"{station.get('einrichtung_name', '')} – {station['name']}", title_style))
    elements.append(Paragraph(
        f"Uebersicht | Stand: {datetime.now().strftime('%d.%m.%Y %H:%M')} | "
        f"{len(patienten)} Bewohner",
        info_style
    ))
    elements.append(Spacer(1, 8*mm))

    if not patienten:
        elements.append(Paragraph("Keine Patienten in dieser Station.", info_style))
    else:
        header = ['Name', 'Geb.-Datum', 'CAVE', 'Letzter Besuch']
        table_data = [header]

        for p in patienten:
            row = [
                Paragraph(f"{p['nachname']}, {p['vorname']}", cell_style),
                Paragraph(format_datum(p.get('geburtsdatum')), cell_style),
                Paragraph(p.get('cave', '') or '–',
                          cave_style if p.get('cave') else cell_style),
                Paragraph(format_datum(p.get('letzter_besuch')), cell_style),
            ]
            table_data.append(row)

        col_widths = [5*cm, 2.5*cm, 5.5*cm, 3*cm]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2d3050')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return buffer


def generate_station_erweitert_pdf(station, patienten_mit_impfungen):
    """
    Generiert ein PDF fuer die erweiterte Liste einer Station
    (mit Impfungen, CAVE und Notizen).
    station: Dict mit Stationsdaten.
    patienten_mit_impfungen: Liste mit dicts {daten: ..., impfungen: [...]}.
    Gibt: BytesIO-Objekt mit dem PDF zurueck.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleCustom', parent=styles['Title'],
                                  fontSize=16, spaceAfter=6*mm)
    info_style = ParagraphStyle('Info', parent=styles['Normal'],
                                 fontSize=9, textColor=colors.HexColor('#555555'))
    cell_style = ParagraphStyle('Cell', parent=styles['Normal'], fontSize=8)
    cave_style = ParagraphStyle('Cave', parent=styles['Normal'],
                                 fontSize=8, textColor=colors.HexColor('#cc0000'))

    elements = []

    elements.append(Paragraph(
        f"{station.get('einrichtung_name', '')} – {station['name']}", title_style))
    elements.append(Paragraph(
        f"Erweiterte Liste | Stand: {datetime.now().strftime('%d.%m.%Y %H:%M')} | "
        f"{len(patienten_mit_impfungen)} Bewohner",
        info_style
    ))
    elements.append(Spacer(1, 8*mm))

    if not patienten_mit_impfungen:
        elements.append(Paragraph("Keine Patienten in dieser Station.", info_style))
    else:
        header = ['Bewohner', 'Offene Impfungen', 'CAVE / Notizen']
        table_data = [header]

        for b in patienten_mit_impfungen:
            patient = b['daten'] if isinstance(b['daten'], dict) else dict(b['daten'])
            impfungen = b['impfungen']

            # Name mit Geburtsdatum
            name_str = f"{patient['nachname']}, {patient['vorname']}"
            geb = format_datum(patient.get('geburtsdatum'))
            if geb:
                name_str += f"<br/><font size='7' color='#888888'>* {geb}</font>"

            # Impfungen formatieren
            impf_texte = []
            for imp in impfungen:
                imp_dict = imp if isinstance(imp, dict) else dict(imp)
                status = STATUS_LABELS.get(imp_dict.get('status', ''), imp_dict.get('status', ''))
                ev = EINVERSTAENDNIS_LABELS.get(
                    imp_dict.get('einverstaendnis_status', ''),
                    imp_dict.get('einverstaendnis_status', '')
                )
                impf_texte.append(f"{imp_dict['impftyp']}: {status} (EV: {ev})")
            impf_str = '<br/>'.join(impf_texte) if impf_texte else 'Keine'

            # CAVE / Notizen
            cave_parts = []
            if patient.get('cave'):
                cave_parts.append(f"<font color='#cc0000'><b>CAVE: {patient['cave']}</b></font>")
            if patient.get('notizen'):
                cave_parts.append(patient['notizen'])
            cave_str = '<br/>'.join(cave_parts) if cave_parts else '–'

            row = [
                Paragraph(name_str, cell_style),
                Paragraph(impf_str, cell_style),
                Paragraph(cave_str, cave_style if patient.get('cave') else cell_style),
            ]
            table_data.append(row)

        col_widths = [4.5*cm, 6.5*cm, 7*cm]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2d3050')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return buffer


def generate_tagesplan_pdf(plan_data, praxis_name='Praxis'):
    """
    Generiert ein PDF mit dem Tagesplan (Routen pro Behandler).
    plan_data: Dict mit 'datum', 'praxis_name', 'routen' (Liste pro Behandler)
    Gibt: BytesIO-Objekt mit dem PDF zurueck.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleCustom', parent=styles['Title'],
                                  fontSize=16, spaceAfter=6*mm)
    subtitle_style = ParagraphStyle('SubTitle', parent=styles['Heading2'],
                                     fontSize=13, spaceAfter=4*mm)
    info_style = ParagraphStyle('Info', parent=styles['Normal'],
                                 fontSize=9, textColor=colors.HexColor('#555555'))
    cell_style = ParagraphStyle('Cell', parent=styles['Normal'], fontSize=8)
    cave_style = ParagraphStyle('Cave', parent=styles['Normal'],
                                 fontSize=8, textColor=colors.HexColor('#cc0000'))

    elements = []

    datum_str = plan_data.get('datum', datetime.now().strftime('%d.%m.%Y'))
    elements.append(Paragraph(f"Tagesplan: {datum_str}", title_style))
    elements.append(Paragraph(
        f"Erstellt: {datetime.now().strftime('%d.%m.%Y %H:%M')} | {praxis_name}",
        info_style
    ))
    elements.append(Spacer(1, 8*mm))

    for route_data in plan_data.get('routen', []):
        behandler = route_data.get('behandler', {})
        besuche = route_data.get('besuche', [])
        stats = route_data.get('stats', {})

        elements.append(Paragraph(
            f"{behandler.get('name', '–')} ({behandler.get('rolle', '')})",
            subtitle_style
        ))

        # Statistik-Zeile
        elements.append(Paragraph(
            f"Stopps: {len(besuche)} | "
            f"Fahrzeit: ~{stats.get('gesamt_fahrzeit_min', 0)} Min. | "
            f"Aufenthalt: ~{stats.get('gesamt_besuchszeit_min', 0)} Min. | "
            f"Distanz: ~{stats.get('gesamt_distanz_km', 0)} km",
            info_style
        ))
        elements.append(Spacer(1, 4*mm))

        if not besuche:
            elements.append(Paragraph("Keine Besuche zugeordnet.", info_style))
            elements.append(Spacer(1, 6*mm))
            continue

        header = ['#', 'Typ', 'Name / Ziel', 'Adresse', 'CAVE / Info', 'Dauer']
        table_data = [header]

        for idx, b in enumerate(besuche, 1):
            typ_icon = "H" if b.get('_typ') == 'P' else "S" # H=Hausbesuch, S=Station
            
            if b.get('_typ') == 'P':
                name = f"{b.get('nachname', '')}, {b.get('vorname', '')}"
                info = b.get('cave', '') or '–'
                adresse = b.get('adresse', '') or ''
                if b.get('einrichtung_name'):
                    adresse = f"{b['einrichtung_name']}"
                    if b.get('station_name'):
                        adresse += f" / {b['station_name']}"
            else:
                name = f"{b.get('einrichtung_name', '')} / {b.get('name', '')}"
                info = "Stationsvisite"
                adresse = b.get('adresse', '') or ''

            row = [
                Paragraph(str(idx), cell_style),
                Paragraph(typ_icon, cell_style),
                Paragraph(name, cell_style),
                Paragraph(adresse, cell_style),
                Paragraph(info, cave_style if b.get('_typ') == 'P' and b.get('cave') else cell_style),
                Paragraph(f"{b.get('besuchsdauer_minuten', 30)} Min.", cell_style),
            ]
            table_data.append(row)

        col_widths = [0.8*cm, 0.8*cm, 4*cm, 4*cm, 4.5*cm, 1.5*cm]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2d3050')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 10*mm))

    doc.build(elements)
    buffer.seek(0)
    return buffer
