# Lighting Automation Studio

A Django-based web application that automatically places lights, switches, and fans in CAD floor plans (DXF/DWG files) based on room and door geometry.

## 📋 Table of Contents

- [Overview](#overview)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)

## 🎯 Overview

This application processes CAD floor plans by:
1. Detecting rooms (closed polylines on `ROOM` layer) and doors (block inserts on `DOOR` layer)
2. Applying configurable automation rules to place:
   - **LIGHT_BLOCK** inserts at room centroids
   - **SWITCH_BLOCK** inserts near doors along walls
   - **FAN_BLOCK** inserts at room centroids
3. Generating an `after.dxf` file with all placements

## 🛠 Tech Stack

### Backend

- **Framework**: Django 5.1+ (Python web framework)
- **CAD Processing**:
  - `ezdxf` (v1.3+) - DXF file parsing and manipulation
  - `shapely` (v2.0+) - Geometric operations for room/door detection
- **Utilities**:
  - `python-dotenv` (v1.0+) - Environment variable management
  - `matplotlib` (v3.8+) - Used internally by ezdxf for drawing operations
- **Database**: SQLite3 (default, can be changed in settings)

### Frontend

- **Templates**: Django template engine (server-side rendering)
- **Styling**: Custom CSS (no framework dependencies)
- **UI Features**:
  - Dark theme interface
  - Responsive grid layouts
  - Form handling with validation
  - File upload interface
  - Status indicators and metrics display

## 📦 Prerequisites

- **Python**: 3.11 or higher
- **pip**: Python package manager
- **Optional**: DWG to DXF converter (if you need to process DWG files)
  - Example: ODA File Converter
  - Or any command-line tool that can convert DWG → DXF

## 🚀 Installation

### Step 1: Clone or Navigate to Project Directory

```bash
cd /path/to/revit_autocad_poc
```

### Step 2: Create Virtual Environment

```bash
python3 -m venv env
```

### Step 3: Activate Virtual Environment

**On macOS/Linux:**
```bash
source env/bin/activate
```

**On Windows:**
```bash
env\Scripts\activate
```

### Step 4: Install Dependencies

```bash
pip install -r requirements.txt
```

This will install:
- Django>=5.1,<5.3
- python-dotenv>=1.0
- ezdxf>=1.3
- shapely>=2.0
- matplotlib>=3.8

### Step 5: Run Database Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

This creates the SQLite database and necessary tables.

## ⚙️ Configuration

### Environment Variables (.env file)

Create a `.env` file in the **project root directory** (same level as `manage.py`):

```bash
# Example .env file location:
/Users/mac/Desktop/revit_autocad_poc/.env
```

### Required Environment Variables

#### 1. Django Secret Key (Optional for development)

If you want to use environment variables for Django settings, add:

```env
SECRET_KEY=your-secret-key-here
DEBUG=True
```

**Note**: The project currently has a default secret key in `settings.py` for development. For production, you should:
- Set `SECRET_KEY` via environment variable
- Set `DEBUG=False`
- Configure `ALLOWED_HOSTS`

#### 2. DWG Converter Command (Optional)

If you need to process DWG files, configure the converter:

```env
DWG_CONVERTER_CMD="ODAFileConverter {input} {output}"
```

**Alternative examples:**
```env
# Using LibreCAD converter
DWG_CONVERTER_CMD="libreoffice --headless --convert-to dxf {input} --outdir {output_dir}"

# Using custom script
DWG_CONVERTER_CMD="/path/to/your/converter.sh {input} {output}"
```

**Important Notes:**
- The command template must include `{input}` and `{output}` placeholders
- If `DWG_CONVERTER_CMD` is not set, DWG uploads will fail with a clear error message
- DXF files work without any converter configuration

### Example .env File

```env
# Django Settings
SECRET_KEY=django-insecure-your-key-here-change-in-production
DEBUG=True

# DWG Converter (optional - only needed for DWG file support)
DWG_CONVERTER_CMD="ODAFileConverter {input} {output}"
```

### Loading Environment Variables

The project uses `python-dotenv`. To load variables automatically, ensure your Django settings include:

```python
from dotenv import load_dotenv
load_dotenv()
```

**Note**: Currently, the project reads `DWG_CONVERTER_CMD` directly via `os.getenv()`. If you want to use `.env` for Django settings, you'll need to add `python-dotenv` loading in `settings.py`.

## ▶️ Running the Application

### Development Server

1. **Activate your virtual environment** (if not already active):
   ```bash
   source env/bin/activate  # macOS/Linux
   # or
   env\Scripts\activate     # Windows
   ```

2. **Start the Django development server**:
   ```bash
   python manage.py runserver
   ```

3. **Access the application**:
   Open your browser and navigate to:
   ```
   http://127.0.0.1:8000/
   ```

### Production Deployment

For production, use a proper WSGI server like Gunicorn or uWSGI:

```bash
pip install gunicorn
gunicorn revit_autocad_poc.wsgi:application
```

**Remember to**:
- Set `DEBUG=False` in settings
- Configure `ALLOWED_HOSTS`
- Use a production database (PostgreSQL, MySQL, etc.)
- Set up proper static file serving
- Use environment variables for sensitive settings

## 📖 Usage

### 1. Prepare Your CAD Drawing

Your DXF/DWG file must follow these conventions:

- **ROOM Layer**: Closed polylines (LWPOLYLINE) representing each room or space
- **DOOR Layer**: Block inserts (INSERT entities) representing door positions
- **Units**: Plans should be in millimetres for sensible spacing

### 2. Upload and Configure

1. Go to the home page (`http://127.0.0.1:8000/`)
2. Fill in the form:
   - **Plan name** (optional): Give your plan a descriptive name
   - **Drawing file**: Select your DXF or DWG file
   - **Automation rules**:
     - Lights per room (default: 4)
     - Switches per door (default: 2)
     - Fans per room (default: 1)
3. Click **"Run automation"**

### 3. Review Results

- The application will:
  - Detect rooms and doors
  - Place blocks according to your rules
  - Generate an `after.dxf` file
- On the detail page, you can:
  - Download the original file
  - Download the processed `after.dxf`
  - View processing logs and metrics (rooms detected, doors detected)

### 4. Open in CAD Software

Open the downloaded `after.dxf` in AutoCAD, Revit, or any DXF-compatible viewer to review the block placements.

## 📁 Project Structure

```
revit_autocad_poc/
├── automation/                 # Main Django app
│   ├── migrations/            # Database migrations
│   ├── services/               # Business logic
│   │   ├── cad_adapters.py   # Room/door detection
│   │   ├── processor.py      # Main processing logic
│   │   └── preview.py         # Preview generation (optional)
│   ├── static/
│   │   └── automation/
│   │       └── style.css     # Frontend styles
│   ├── templates/
│   │   └── automation/
│   │       ├── base.html     # Base template
│   │       ├── upload.html   # Upload page
│   │       └── detail.html  # Results page
│   ├── models.py              # Database models
│   ├── views.py              # View handlers
│   └── urls.py               # URL routing
├── revit_autocad_poc/        # Django project settings
│   ├── settings.py           # Django configuration
│   ├── urls.py               # Root URL config
│   └── wsgi.py               # WSGI entry point
├── media/                    # User uploads and outputs
│   ├── uploads/              # Original files
│   └── outputs/              # Generated after.dxf files
├── db.sqlite3                # SQLite database (created after migrate)
├── manage.py                 # Django management script
├── requirements.txt          # Python dependencies
├── .env                      # Environment variables (create this)
└── README.md                 # This file
```

## 🔧 Troubleshooting

### Issue: "DWG_CONVERTER_CMD not configured"

**Solution**: 
- If you only need DXF support, ignore this error and upload DXF files only
- If you need DWG support, create a `.env` file in the project root with:
  ```env
  DWG_CONVERTER_CMD="your-converter-command {input} {output}"
  ```

### Issue: "No rooms or doors detected"

**Possible causes**:
- Your drawing doesn't use `ROOM` and `DOOR` layer names exactly
- Rooms aren't closed polylines
- Doors aren't INSERT entities

**Solution**: Check your CAD file layer names and entity types match the requirements.

### Issue: Database errors

**Solution**: Run migrations again:
```bash
python manage.py migrate
```

### Issue: Static files not loading

**Solution**: Collect static files (for production):
```bash
python manage.py collectstatic
```

### Issue: Port 8000 already in use

**Solution**: Run on a different port:
```bash
python manage.py runserver 8080
```

## 📝 Notes

- This is a **proof-of-concept** application
- Processing runs **synchronously** (for production, consider background tasks)
- The database uses **SQLite** by default (suitable for development)
- File uploads are stored in the `media/` directory

## 🤝 Contributing

Feel free to submit issues or pull requests for improvements.

## 📄 License

This project is provided as-is for demonstration purposes.
