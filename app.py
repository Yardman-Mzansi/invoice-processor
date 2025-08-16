import os
import re
import io
from flask import Flask, render_template, request, jsonify, send_file
import PyPDF2
import pandas as pd
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

class InvoiceExtractor:
    def __init__(self):
        self.extracted_data = []
    
    def extract_text_from_pdf(self, pdf_path):
        """Extract text from PDF file"""
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text()
                return text
        except Exception as e:
            print(f"Error reading PDF {pdf_path}: {str(e)}")
            return ""
    
    def parse_invoice_data(self, text, filename):
        """Parse invoice data from extracted text"""
        try:
            # Extract date
            date_pattern = r'(\d{2}-\d{2}-\d{4})'
            date_match = re.search(date_pattern, text)
            date = date_match.group(1) if date_match else ""
            
            # Extract Our Reference
            ref_pattern = r'INV(\d+)'
            ref_match = re.search(ref_pattern, text)
            our_reference = f"INV{ref_match.group(1)}" if ref_match else ""
            
            # Extract Total (Excl) and Total (Incl)
            total_excl_pattern = r'Total \(Excl\)\s+([\d,]+\.?\d*)'
            total_incl_pattern = r'Total \(Incl\)\s+([\d,]+\.?\d*)'
            
            total_excl_match = re.search(total_excl_pattern, text)
            total_incl_match = re.search(total_incl_pattern, text)
            
            total_excl = float(total_excl_match.group(1).replace(',', '')) if total_excl_match else 0
            total_incl = float(total_incl_match.group(1).replace(',', '')) if total_incl_match else 0
            
            # Extract line items
            items = self.extract_line_items(text)
            
            # Create invoice record
            invoice_data = {
                'filename': filename,
                'date': date,
                'our_reference': our_reference,
                'total_excl': total_excl,
                'total_incl': total_incl,
                'items': items
            }
            
            return invoice_data
            
        except Exception as e:
            print(f"Error parsing invoice data: {str(e)}")
            return None
    
    def extract_line_items(self, text):
        """Extract line items from invoice text"""
        items = []
        
        # Split text into lines for more precise parsing
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or 'Item Code' in line or 'Item Description' in line:
                continue
            
            # Pattern 1: General format with potential Tax column
            # Tries to match: Code Description Quantity [Unit] Price Tax Total
            general_pattern = r'^(\S+)\s+(.+?)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)$'
            match = re.match(general_pattern, line)
            
            if match and len(match.groups()) == 6:
                try:
                    code = match.group(1)
                    desc = match.group(2).strip()
                    qty = float(match.group(3).replace(',', ''))
                    price = float(match.group(4).replace(',', ''))
                    tax = float(match.group(5).replace(',', ''))
                    total = float(match.group(6).replace(',', ''))
                    
                    # Validation: check if calculations make sense for quantity * price ≈ total
                    expected_total = qty * price
                    if abs(total - expected_total) < expected_total * 0.1:  # Within 10%
                        items.append({
                            'item_code': code,
                            'description': desc,
                            'quantity': qty,
                            'unit': '',
                            'price': price,
                            'tax': tax,
                            'total': total
                        })
                        continue
                        
                except ValueError:
                    pass
            
            # Pattern 2: Express Petroleum fuel patterns (verified format)
            # Format: "LSD : EL LOW SULPHUR DIESEL : EL 20,049.00 24.1264 483,710.19"
            # Structure: ItemCode Description Quantity Price Total
            express_fuel_pattern = r'^([A-Z]+\s*:\s*EL)\s+([A-Z\s:]+)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)$'
            express_match = re.match(express_fuel_pattern, line)
            
            if express_match:
                item_code = express_match.group(1).strip()
                description = express_match.group(2).strip()
                quantity = float(express_match.group(3).replace(',', ''))
                price = float(express_match.group(4).replace(',', ''))
                total = float(express_match.group(5).replace(',', ''))
                
                # Verify calculation: quantity * price should equal total
                calculated_total = quantity * price
                if abs(calculated_total - total) < max(total * 0.01, 0.01):  # Within 1% or 1 cent
                    items.append({
                        'item_code': item_code,
                        'description': description,
                        'quantity': quantity,
                        'unit': '',
                        'price': price,
                        'tax': 0.0,
                        'total': total
                    })
                    continue
            
            # Pattern 2b: Express Petroleum alternate format (with item numbers)
            # Format: "LSD : EL 84215 14,874.00 23.7297 352,955.56" or "PETROL : E 84217,84216 20,324.00 20.6990 420,686.48"
            # Structure: ItemCode ItemNumbers Quantity Price Total
            express_alt_pattern = r'^([A-Z]+\s*:\s*E[L]?)\s+([A-Z0-9,]+)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)$'
            express_alt_match = re.match(express_alt_pattern, line)
            
            if express_alt_match:
                item_code = express_alt_match.group(1).strip()
                item_numbers = express_alt_match.group(2).strip()
                quantity = float(express_alt_match.group(3).replace(',', ''))
                price = float(express_alt_match.group(4).replace(',', ''))
                total = float(express_alt_match.group(5).replace(',', ''))
                
                # Create description from item code
                if 'LSD' in item_code:
                    description = 'LOW SULPHUR DIESEL : EL'
                elif 'PETROL' in item_code:
                    description = 'PETROL : EL'
                else:
                    description = item_code
                
                # Verify calculation: quantity * price should equal total
                calculated_total = quantity * price
                if abs(calculated_total - total) < max(total * 0.01, 0.01):  # Within 1% or 1 cent
                    items.append({
                        'item_code': item_code,
                        'description': description,
                        'quantity': quantity,
                        'unit': '',
                        'price': price,
                        'tax': 0.0,
                        'total': total
                    })
                    continue
            
            # Pattern 3: Legacy fuel patterns (fallback for other formats)
            legacy_fuel_pattern = r'([A-Z\s:]+)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)'
            legacy_match = re.search(legacy_fuel_pattern, line)
            
            if legacy_match:
                desc = legacy_match.group(1).strip()
                val1 = float(legacy_match.group(2).replace(',', ''))
                val2 = float(legacy_match.group(3).replace(',', ''))
                val3 = float(legacy_match.group(4).replace(',', ''))
                
                # Check if this looks like fuel product
                if any(fuel in desc.upper() for fuel in ['DIESEL', 'PETROL', 'PARAFFIN', 'EL']):
                    # Try to identify which is quantity, price, total by checking calculations
                    # Usually: val1=quantity, val2=price, val3=total
                    if abs(val3 - (val1 * val2)) < val3 * 0.01:  # val3 = val1 * val2 (within 1%)
                        qty, price, total = val1, val2, val3
                    # Sometimes: val1=total, val2=quantity, val3=price  
                    elif abs(val1 - (val2 * val3)) < val1 * 0.01:  # val1 = val2 * val3
                        qty, price, total = val2, val3, val1
                    # Or: val1=quantity, val2=total, val3=price
                    elif abs(val2 - (val1 * val3)) < val2 * 0.01:  # val2 = val1 * val3
                        qty, price, total = val1, val3, val2
                    else:
                        # Default assumption: quantity, price, total
                        qty, price, total = val1, val2, val3
                    
                    items.append({
                        'item_code': '',
                        'description': desc,
                        'quantity': qty,
                        'unit': '',
                        'price': price,
                        'tax': 0.0,
                        'total': total
                    })
                    continue
        
        return items
    
    def process_folder(self, folder_path):
        """Process all PDF files in a folder"""
        self.extracted_data = []
        
        for filename in os.listdir(folder_path):
            if filename.lower().endswith('.pdf'):
                pdf_path = os.path.join(folder_path, filename)
                text = self.extract_text_from_pdf(pdf_path)
                
                if text:
                    invoice_data = self.parse_invoice_data(text, filename)
                    if invoice_data:
                        self.extracted_data.append(invoice_data)
        
        return self.extracted_data
    
    def convert_to_excel_format(self):
        """Convert extracted data to Excel-ready format"""
        excel_data = []
        
        for invoice in self.extracted_data:
            # Calculate total expected from all line items
            # Use the extracted total values which are already validated
            total_expected = sum(item['total'] + item.get('tax', 0) for item in invoice['items'])
            
            # Create base row with invoice info
            row = {
                'Filename': invoice['filename'],
                'Date': invoice['date'],
                'Our Reference': invoice['our_reference'],
                'Total Expected': total_expected,
                'Total (Incl)': invoice['total_incl']
            }
            
            # Add up to 3 items (can be extended)
            for i in range(3):
                if i < len(invoice['items']):
                    item = invoice['items'][i]
                    row[f'Item {i+1} Code'] = item.get('item_code', '')
                    row[f'Item {i+1} Description'] = item['description']
                    row[f'Item {i+1} Quantity'] = item['quantity']
                    row[f'Item {i+1} Unit'] = item.get('unit', '')
                    row[f'Item {i+1} Price (Ex)'] = item['price']
                    row[f'Item {i+1} Tax'] = item.get('tax', 0)
                    row[f'Item {i+1} Total Rand'] = item['total']
                else:
                    row[f'Item {i+1} Code'] = ''
                    row[f'Item {i+1} Description'] = ''
                    row[f'Item {i+1} Quantity'] = ''
                    row[f'Item {i+1} Unit'] = ''
                    row[f'Item {i+1} Price (Ex)'] = ''
                    row[f'Item {i+1} Tax'] = ''
                    row[f'Item {i+1} Total Rand'] = ''
            
            excel_data.append(row)
        
        return excel_data

# Global extractor instance
extractor = InvoiceExtractor()

@app.route('/')
def index():
    """Main page for uploading PDFs"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_files():
    """Handle PDF file uploads"""
    if 'files' not in request.files:
        return jsonify({'error': 'No files uploaded'}), 400
    
    files = request.files.getlist('files')
    uploaded_files = []
    
    # Clear upload folder
    for file in os.listdir(app.config['UPLOAD_FOLDER']):
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], file))
    
    # Save uploaded files
    for file in files:
        if file and file.filename.lower().endswith('.pdf'):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            uploaded_files.append(filename)
    
    if not uploaded_files:
        return jsonify({'error': 'No valid PDF files uploaded'}), 400
    
    # Process uploaded files
    extracted_data = extractor.process_folder(app.config['UPLOAD_FOLDER'])
    
    return jsonify({
        'success': True,
        'files_processed': len(uploaded_files),
        'data_extracted': len(extracted_data)
    })

@app.route('/results')
def results():
    """Display extracted data"""
    excel_data = extractor.convert_to_excel_format()
    
    # Calculate summary stats
    total_invoices = len(excel_data)
    total_value_expected = sum(row['Total Expected'] for row in excel_data)
    total_value_incl = sum(row['Total (Incl)'] for row in excel_data)
    
    summary = {
        'total_invoices': total_invoices,
        'total_value_expected': total_value_expected,
        'total_value_incl': total_value_incl
    }
    
    return render_template('results.html', data=excel_data, summary=summary)

@app.route('/download')
def download_excel():
    """Download extracted data as Excel file"""
    excel_data = extractor.convert_to_excel_format()
    
    if not excel_data:
        return jsonify({'error': 'No data to download'}), 400
    
    # Create DataFrame and Excel file
    df = pd.DataFrame(excel_data)
    
    # Create Excel file in memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Invoice Data')
    
    output.seek(0)
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'invoice_data_{timestamp}.xlsx'
    
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@app.route('/api/data')
def get_data():
    """API endpoint to get extracted data as JSON"""
    return jsonify(extractor.convert_to_excel_format())

@app.route('/debug')
def debug_extraction():
    """Debug endpoint to show detailed extraction information"""
    debug_data = []
    
    for invoice in extractor.extracted_data:
        total_expected = sum(item['total'] + item.get('tax', 0) for item in invoice['items'])
        discrepancy = abs(total_expected - invoice['total_incl'])
        
        debug_info = {
            'filename': invoice['filename'],
            'date': invoice['date'],
            'our_reference': invoice['our_reference'],
            'total_incl': invoice['total_incl'],
            'total_expected': total_expected,
            'discrepancy': discrepancy,
            'discrepancy_percent': (discrepancy / invoice['total_incl'] * 100) if invoice['total_incl'] > 0 else 0,
            'items_found': len(invoice['items']),
            'items': invoice['items']
        }
        debug_data.append(debug_info)
    
    debug_summary = {
        'debug_data': debug_data,
        'total_invoices': len(debug_data),
        'high_discrepancy_count': len([d for d in debug_data if d['discrepancy_percent'] > 5])
    }
    
    return render_template('debug.html', debug_info=debug_summary)

if __name__ == '__main__':
    app.run(debug=True)