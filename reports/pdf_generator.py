import sys
import os
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from datetime import datetime

# Add parent directory to path to allow database and config import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from database.db import get_incident_by_id

def generate_incident_pdf(incident_id, output_path):
    """
    Generates a professional PDF report for a specific incident.
    """
    incident = get_incident_by_id(incident_id)
    if not incident:
        raise ValueError(f"Incident with ID {incident_id} not found in database.")

    # Create document template
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )
    
    # Styles
    styles = getSampleStyleSheet()
    
    # Custom Styles
    primary_color = colors.HexColor('#0F172A')   # Navy/Slate Dark
    secondary_color = colors.HexColor('#1E293B') # Slightly lighter slate
    accent_color = colors.HexColor('#0284C7')    # Sky blue
    
    title_style = ParagraphStyle(
        'ReportTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=primary_color,
        spaceAfter=15
    )
    
    section_heading = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=secondary_color,
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True
    )
    
    body_style = ParagraphStyle(
        'ReportBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#334155'),
        spaceAfter=8
    )
    
    bold_body_style = ParagraphStyle(
        'ReportBoldBody',
        parent=body_style,
        fontName='Helvetica-Bold'
    )
    
    # Risk Badge styles
    risk_level = incident['risk_level'].upper()
    if risk_level == 'HIGH':
        badge_bg = colors.HexColor('#FEE2E2') # soft red
        badge_text = colors.HexColor('#991B1B') # dark red
    elif risk_level == 'MODERATE':
        badge_bg = colors.HexColor('#FEF3C7') # soft orange/yellow
        badge_text = colors.HexColor('#92400E') # dark orange
    else:
        badge_bg = colors.HexColor('#ECFDF5') # soft green
        badge_text = colors.HexColor('#065F46') # dark green
        
    badge_style = ParagraphStyle(
        'RiskBadge',
        parent=body_style,
        fontName='Helvetica-Bold',
        fontSize=11,
        textColor=badge_text,
        alignment=1 # Center aligned
    )

    flowables = []
    
    # 1. Header Table (Title and Risk Level)
    header_data = [
        [
            Paragraph("ROAD ACCIDENT ANALYSIS REPORT", title_style),
            Table(
                [[Paragraph(f"<b>{risk_level} RISK</b>", badge_style)]],
                colWidths=[120],
                style=TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), badge_bg),
                    ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                    ('TOPPADDING', (0,0), (-1,-1), 8),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 8),
                    ('BOX', (0,0), (-1,-1), 1.5, badge_text),
                ])
            )
        ]
    ]
    
    header_table = Table(header_data, colWidths=[380, 140])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
    ]))
    flowables.append(header_table)
    
    # Decorative colored bar
    flowables.append(Table([['']], colWidths=[520], rowHeights=[3], style=TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), accent_color),
        ('BOTTOMPADDING', (0,0), (-1,-1), 15),
    ])))
    flowables.append(Spacer(1, 10))
    
    # 2. General Incident Metadata Table
    meta_data = [
        [Paragraph("<b>Incident ID:</b>", bold_body_style), Paragraph(f"#{incident['id']}", body_style),
         Paragraph("<b>Date & Time:</b>", bold_body_style), Paragraph(incident['timestamp'], body_style)],
        [Paragraph("<b>Incident Type:</b>", bold_body_style), Paragraph(incident['incident_type'], body_style),
         Paragraph("<b>Resolution Status:</b>", bold_body_style), Paragraph("RESOLVED" if incident['resolved'] else "ACTIVE / INVESTIGATING", body_style)],
        [Paragraph("<b>Vehicle ID:</b>", bold_body_style), Paragraph(f"#{incident['vehicle_id']}" if incident['vehicle_id'] else "N/A", body_style),
         Paragraph("<b>Person ID:</b>", bold_body_style), Paragraph(f"#{incident['person_id']}" if incident['person_id'] else "N/A", body_style)]
    ]
    
    meta_table = Table(meta_data, colWidths=[100, 160, 110, 150])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#F1F5F9')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    flowables.append(meta_table)
    flowables.append(Spacer(1, 15))
    
    # 3. Description
    flowables.append(Paragraph("Incident Description & System Log", section_heading))
    desc_text = incident.get('description', '')
    if not desc_text:
        desc_text = f"A {incident['incident_type']} was detected by the traffic monitoring AI at {incident['timestamp']}. "
        if incident['vehicle_id']:
            desc_text += f"The event involved vehicle ID #{incident['vehicle_id']}. "
        if incident['person_id']:
            desc_text += f"Pedestrian ID #{incident['person_id']} was identified in proximity."
            
    flowables.append(Paragraph(desc_text, body_style))
    flowables.append(Spacer(1, 10))
    
    # 4. Embedded Screenshot Evidence
    flowables.append(Paragraph("Evidence Capture (Screenshot)", section_heading))
    screenshot_path = incident['screenshot_path']
    
    if screenshot_path:
        # Check if it is a relative path or absolute path
        abs_screenshot_path = screenshot_path
        if not os.path.isabs(screenshot_path):
            abs_screenshot_path = os.path.join(config.BASE_DIR, screenshot_path)
            
        if os.path.exists(abs_screenshot_path):
            try:
                # Add image - scaled to fit letter width nicely
                img_width = 460
                img_height = 258 # Maintains 16:9 ratio
                img_flowable = Image(abs_screenshot_path, width=img_width, height=img_height)
                
                # Center the image inside a table
                img_table = Table([[img_flowable]], colWidths=[520])
                img_table.setStyle(TableStyle([
                    ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                    ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#CBD5E1')),
                    ('TOPPADDING', (0,0), (-1,-1), 4),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ]))
                flowables.append(img_table)
            except Exception as e:
                flowables.append(Paragraph(f"<i>Error rendering evidence screenshot: {str(e)}</i>", body_style))
        else:
            flowables.append(Paragraph(f"<i>Screenshot file not found on server ({screenshot_path}).</i>", body_style))
    else:
        flowables.append(Paragraph("<i>No screenshot evidence was logged for this low-risk/abrupt event.</i>", body_style))
        
    flowables.append(Spacer(1, 15))
    
    # 5. Video Evidence Reference
    flowables.append(Paragraph("Video Evidence File Reference", section_heading))
    video_path = incident['video_path']
    if video_path:
        flowables.append(Paragraph(f"A 20-second video evidence clip has been saved on the host machine at:<br/><code>{video_path}</code><br/>This clip encompasses 10 seconds prior to and 10 seconds after the collision event trigger timestamp.", body_style))
    else:
        flowables.append(Paragraph("No automatic video recording was triggered (only high/moderate risk events log continuous video).", body_style))
        
    flowables.append(Spacer(1, 20))
    
    # 6. Footer disclaimer
    footer_text = f"Report generated automatically on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} by the Road Accident Detection & Emergency Alert System. AI-generated warnings require human validation."
    flowables.append(Paragraph(f"<font color='#94A3B8'><i>{footer_text}</i></font>", ParagraphStyle('Footer', parent=body_style, fontSize=8, alignment=1)))
    
    # Build Document
    doc.build(flowables)
    print(f"PDF report successfully written to: {output_path}")

if __name__ == '__main__':
    # Test stub
    # init_db() must have been run
    try:
        generate_incident_pdf(1, "test_report.pdf")
    except Exception as e:
        print("Test run note (likely no records yet):", str(e))
