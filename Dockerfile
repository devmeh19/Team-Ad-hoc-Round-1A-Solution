# Use official Python image for AMD64
FROM --platform=linux/amd64 python:3.10-slim

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the main script
COPY process_pdfs.py .

# Set up input/output directories (these will be mounted at runtime)
RUN mkdir -p /app/input /app/output

# Set the entrypoint
CMD ["python", "process_pdfs.py"] 