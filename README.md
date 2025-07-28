Team Ad hoc
Team Members - Dev Mehrotra, Shashwat Tripathi

# Challenge 1a: PDF Processing Solution

## Prerequisite: Install Python
This project requires **Python 3.10 or newer**. If Python is not already installed on your system, follow these steps:

1. Download Python from the official website: https://www.python.org/downloads/
2. Run the installer and **check the box that says "Add Python to PATH"** during installation.
3. Verify installation by running:
   ```sh
   python --version
   ```
   or
   ```sh
   python3 --version
   ```
   You should see output like `Python 3.10.x` or higher.

---

## Overview
This repository contains a solution for Challenge 1a of the Adobe India Hackathon 2025. The challenge is to extract structured data from PDF documents and output them as JSON files, following a specific schema. The solution is fully containerized using Docker and meets all performance and resource constraints.

---

## Project Structure
```
Challenge-1A/
├── input/                # Input PDF files (main folder used by script & Docker)
├── output/               # Output JSON files (main folder used by script & Docker)
├── Dockerfile            # Docker container configuration
├── process_pdfs.py       # Main PDF processing script
├── requirements.txt      # Python dependencies
└── README.md             # This file
```

---

## Requirements
- Python 3.10+
- All dependencies are open source and specified in requirements.txt
- No internet access required at runtime
- Solution runs on CPU (amd64), 8 CPUs, 16GB RAM

---

## How It Works
- All PDFs in `input/` are processed automatically.
- For each PDF, a JSON file is generated in `output/` with the same base filename.
- The output JSON follows a simple schema (see below).

---

## Running Locally (Without Docker)
1. **Install Python dependencies:**
   ```sh
   pip install -r requirements.txt
   ```
2. **Run the script:**
   ```sh
   python process_pdfs.py
   ```
   - Input PDFs: `input/`
   - Output JSONs: `output/`

---

## Running with Docker

### 1. Prepare Input and Output Folders
- In your project root (where the Dockerfile is), create two folders:
  - `input/` (put your test PDFs here)
  - `output/` (leave empty; results will appear here)

### 2. Build the Docker Image
- **PowerShell (Windows):**
  ```powershell
  docker build --platform linux/amd64 -t mysolutionname:somerandomidentifier .
  ```
- **Linux/macOS:**
  ```sh
  docker build --platform linux/amd64 -t mysolutionname:somerandomidentifier .
  ```

### 3. Run the Docker Container
- **PowerShell (Windows):**
  ```powershell
  docker run --rm -v ${PWD}/input:/app/input -v ${PWD}/output:/app/output --network none mysolutionname:somerandomidentifier
  ```
- **Linux/macOS:**
  ```sh
  docker run --rm -v $(pwd)/input:/app/input -v $(pwd)/output:/app/output --network none mysolutionname:somerandomidentifier
  ```

- The container will process all PDFs in `input/` and write a `.json` file for each PDF to `output/`.

---

## Output Format
Each output JSON will look like:
```json
{
  "title": "Document Title",
  "outline": [
    { "level": "H1", "text": "Section Heading", "page": 1 },
    { "level": "H2", "text": "Subsection Heading", "page": 2 }
    // ...
  ]
}
```
- The schema is simple: a title and an outline (list of headings with level, text, and page).

---

## About pdfminer.six

This project uses **pdfminer.six** for PDF text extraction.

### What is pdfminer.six?
- An open-source Python library for extracting text, metadata, and layout information from PDF files.
- Designed for robust, accurate extraction from both simple and complex PDFs.
- Actively maintained and widely used in the Python community.

### Key Features
- **Text Extraction:** Extracts all text, including paragraphs, headings, and inline text.
- **Layout Analysis:** Can detect and preserve the structure of multi-column layouts, tables, and text boxes.
- **Font and Style Detection:** Identifies font sizes, styles, and positions, which is useful for heading detection.
- **Image and Object Skipping:** Can skip images and non-text objects for faster processing.
- **No Internet Required:** Works fully offline.
- **Open Source:** 100% open source and free to use.

### Multilingual Capabilities
- **Unicode Support:** Handles a wide range of languages and scripts, including Latin, Cyrillic, Chinese, Japanese, Korean, Arabic, and more.
- **Complex Scripts:** Supports extraction from PDFs containing mixed languages and complex scripts, provided the PDF text is not embedded as an image.
- **Encoding Robustness:** Handles various PDF encodings and font types.



---

## Notes
- No internet access is required or allowed during runtime.
- All processing is done on CPU.
- The solution is designed for both simple and complex PDFs, and supports multilingual text extraction.
