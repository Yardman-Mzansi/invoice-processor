# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Flask-based web application that processes PDF invoices and extracts structured data for analysis. The application allows users to upload multiple PDF invoices, automatically extracts key information (dates, reference numbers, line items, totals), and provides the results in both web interface and Excel export formats.

## Development Commands

### Environment Setup
```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Application
```bash
# Development server
python app.py

# Production server (if using gunicorn)
gunicorn app:app
```

### Debugging Extraction Issues
- Access `/debug` route after processing invoices to see detailed extraction analysis
- Look for invoices with >5% discrepancy between expected and actual totals
- Check if line items are being extracted correctly
- Verify mathematical calculations: quantity × price = total

### Dependencies
The application uses these key dependencies:
- **Flask**: Web framework
- **PyPDF2**: PDF text extraction
- **pandas**: Data manipulation and Excel export
- **openpyxl**: Excel file creation
- **werkzeug**: File upload security

## Architecture

### Core Components

**`InvoiceExtractor` Class** (`app.py:17-154`)
- Main business logic for PDF processing
- Handles text extraction, data parsing, and format conversion
- Uses regex patterns to extract specific invoice fields
- Converts extracted data to Excel-compatible format

**Flask Routes** (`app.py:159-248`)
- `/` - Main upload interface
- `/upload` - POST endpoint for file processing
- `/results` - Display extracted data
- `/download` - Excel file export
- `/api/data` - JSON API endpoint

**Template Structure**
- `base.html` - Common layout with CSS styling and JavaScript utilities
- `index.html` - File upload interface with drag-and-drop functionality
- `results.html` - Data display table with summary statistics

### Data Flow
1. User uploads PDF files via web interface
2. Files saved to `uploads/` directory (cleared on each upload)
3. `InvoiceExtractor.process_folder()` iterates through PDFs
4. Text extracted using PyPDF2, parsed with regex patterns
5. Structured data stored in `extracted_data` list
6. Results displayed in web interface and/or exported to Excel

### File Processing Logic
- **Text Extraction**: Uses PyPDF2 to extract all text from PDF pages
- **Pattern Matching**: Regex patterns for dates (DD-MM-YYYY), invoice references (INV\d+), totals
- **Line Items**: Enhanced multi-pattern extraction system:
  - **General Pattern**: Handles most invoice formats with validation
  - **Fuel Pattern**: Specialized for fuel industry invoices
  - **Flexible Parsing**: Adapts to different column arrangements
- **Error Handling**: Graceful handling of PDF reading errors and parsing failures
- **Validation**: Mathematical validation of extracted values (quantity × price ≈ total)

### Key Patterns for Invoice Data
- Date format: `\d{2}-\d{2}-\d{4}`
- Invoice reference: `INV\d+`
- Total amounts: `Total \(Excl\)\s+([\d,]+\.?\d*)` and `Total \(Incl\)\s+([\d,]+\.?\d*)`
- Line items: Multi-tier parsing strategy:
  - **Tier 1 - General**: With Tax column (Code Description Quantity Price Tax Total)
  - **Tier 2a - Express Standard**: `^([A-Z]+\s*:\s*EL)\s+([A-Z\s:]+)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)$`
  - **Tier 2b - Express Alternate**: `^([A-Z]+\s*:\s*E[L]?)\s+([A-Z0-9,]+)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)$`
  - **Tier 3 - Legacy**: Flexible patterns with mathematical validation

## Important Implementation Details

### File Security
- Uses `werkzeug.secure_filename()` for upload security
- Validates PDF file extensions
- 16MB upload size limit configured
- Upload directory cleared between sessions

### Data Structure
Each processed invoice creates a dictionary with:
- `filename`, `date`, `our_reference`
- `total_excl`, `total_incl` (financial totals)
- `items` array with enhanced line item data:
  - `item_code`: Product/service code
  - `description`: Item description
  - `quantity`: Quantity ordered
  - `unit`: Unit of measurement (if applicable)
  - `price`: Unit price (excluding tax)
  - `tax`: Tax amount per line item
  - `total`: Total amount for line item (excluding tax)

### Excel Export Format
Flattens nested invoice data into spreadsheet columns:
- Core invoice fields (filename, date, reference, totals)
- Up to 3 line items per invoice with columns for:
  - Item Code, Description, Quantity, Unit, Price (Ex), Tax, Total
- **Total Expected**: Calculated as `(quantity × price) + tax` for each line item
- Summary statistics calculated across all invoices

### Frontend Features
- Drag-and-drop file upload with visual feedback
- Progress indicators and loading states
- Client-side file validation (PDF only)
- Responsive design with modern CSS styling
- Currency formatting in ZAR (South African Rand)

## Recent Improvements (Latest Version)

### Enhanced Invoice Processing
- **Multi-Format Support**: Now handles invoices with and without tax columns
- **Express Petroleum Optimized**: Multiple patterns for Express Petroleum invoice variations
  - **Standard Format**: `ItemCode | Description | Quantity | Price | Total`
  - **Alternate Format**: `ItemCode | ItemNumbers | Quantity | Price | Total` (handles missing descriptions)
  - **Edge Cases**: Handles `PETROL : E` vs `PETROL : EL` variations
  - Mathematical validation: `quantity × price = total`
  - Zero discrepancy extraction for Express invoices
- **Improved Pattern Matching**: Three-tier pattern matching system:
  - **Tier 1**: General format with tax columns (uniform invoices)
  - **Tier 2**: Express Petroleum specific format (fuel invoices)
  - **Tier 3**: Legacy fallback patterns (other formats)
- **Validation Logic**: Mathematical validation ensures extracted data makes sense

### Updated Data Structure
Line items now include:
- `item_code`: Product/service identifier
- `unit`: Unit of measurement (when present)
- `tax`: Individual line item tax amounts
- Enhanced `total_expected` calculation: `(quantity × price) + tax`

### Frontend Updates
- Added columns for Item Code, Unit, and Tax in results table
- Improved Excel export with comprehensive line item details
- Better handling of different invoice formats in display
- **Debug Interface**: Added `/debug` route to identify extraction issues
  - Shows discrepancy analysis between expected and actual totals
  - Highlights invoices with >5% discrepancy for investigation
  - Detailed line item extraction breakdown for problematic invoices

## Error Handling Considerations

- PDF reading failures are logged but don't stop processing of other files
- Regex parsing errors result in empty/default values rather than exceptions
- File upload errors return appropriate HTTP status codes
- Frontend handles both success and error responses from API calls
- Mathematical validation prevents invalid data extraction