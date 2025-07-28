import os
import json
from pathlib import Path
from collections import Counter, defaultdict
from typing import List, Dict, Any
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextBoxHorizontal, LTTextLineHorizontal, LTChar, LTImage
from pdfminer.pdfparser import PDFSyntaxError
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfparser import PDFParser
from pdfminer.pdftypes import resolve1
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LAParams
import calendar
MONTHS = {m.lower() for m in list(calendar.month_name) + list(calendar.month_abbr) if m}

INPUT_DIR = Path("input")
OUTPUT_DIR = Path("output")

HEADING_LEVELS = ["H1", "H2", "H3"]

# Regex patterns for headings
import re
HEADING_PATTERNS = [
    re.compile(r"^(chapter|section|part)\\s+\\d+", re.IGNORECASE),
    re.compile(r"^\\d+(\\.\\d+)*\\s+"),
    re.compile(r"^[A-Z][A-Z0-9\\s\-:]{4,}$"),  # ALL CAPS
]

def extract_metadata_title(pdf_path: Path) -> str:
    try:
        with open(pdf_path, 'rb') as f:
            parser = PDFParser(f)
            doc = PDFDocument(parser)
            info = doc.info[0] if doc.info else {}
            title = info.get('Title', b'').decode('utf-8', errors='ignore').strip()
            return title if title else None
    except Exception:
        return None

def extract_font_sizes(lines: List[Dict]) -> List[float]:
    sizes = []
    for line in lines:
        if line['font_size']:
            sizes.append(line['font_size'])
    return sizes

def cluster_font_sizes(sizes: List[float]) -> List[float]:
    # Get the 3 most common largest font sizes
    if not sizes:
        return []
    counter = Counter(sizes)
    most_common = sorted(counter.items(), key=lambda x: (-x[0], -x[1]))
    clusters = [size for size, _ in most_common[:3]]
    return clusters

def is_heading(text: str, font_size: float, clusters: List[float]) -> str:
    # Assign H1/H2/H3 based on font size cluster and pattern
    if not text or not font_size:
        return None
    for i, cluster in enumerate(clusters):
        if abs(font_size - cluster) < 0.5:
            for idx, pat in enumerate(HEADING_PATTERNS):
                if pat.match(text):
                    return HEADING_LEVELS[max(i, idx)]
            return HEADING_LEVELS[i]
    # Pattern match fallback
    for idx, pat in enumerate(HEADING_PATTERNS):
        if pat.match(text):
            return HEADING_LEVELS[min(idx, 2)]
    return None

def extract_lines_with_features(pdf_path: Path) -> List[Dict]:
    lines = []
    for page_num, page_layout in enumerate(extract_pages(pdf_path), 1):
        for element in page_layout:
            if isinstance(element, LTTextBoxHorizontal):
                for line in element:
                    if isinstance(line, LTTextLineHorizontal):
                        text = line.get_text().strip()
                        if not text:
                            continue
                        font_sizes = [char.size for char in line if isinstance(char, LTChar)]
                        font_names = [char.fontname for char in line if isinstance(char, LTChar)]
                        if font_sizes:
                            avg_font_size = sum(font_sizes) / len(font_sizes)
                        else:
                            avg_font_size = None
                        lines.append({
                            'text': text,
                            'font_size': avg_font_size,
                            'font_names': font_names,
                            'page': page_num,
                            'y0': line.y0,
                        })
    return lines

def extract_title(lines: List[Dict], metadata_title: str) -> str:
    if metadata_title:
        return metadata_title
    # Fallback: largest text on first page
    first_page_lines = [l for l in lines if l['page'] == 1 and l['font_size']]
    if not first_page_lines:
        return "Untitled"
    largest = max(first_page_lines, key=lambda l: l['font_size'])
    return largest['text']

FIELD_LABEL_WORDS = {"date", "signature", "rs.", "amount", "designation", "service", "block", "advance", "pay", "name", "place", "headquarters"}

def is_probable_field_label(text, next_text=None):
    # More selective field label detection - don't exclude all numbered items
    t = text.strip().lower()
    if len(t) < 5:  # Only exclude very short labels
        if t in FIELD_LABEL_WORDS:
            return True
        # Only exclude standalone numbers like "1.", "2." if they're very short
        if re.match(r'^\d+\.$', t) and len(t) <= 3:
            return True
    return False

def is_incomplete_heading(text):
    """Check if heading appears to be incomplete or cut off"""
    t = text.strip()
    # Check if ends with common incomplete patterns
    if t.endswith(('the', 'for', 'of', 'in', 'on', 'at', 'to', 'a', 'an', 'and', 'or', 'but')):
        return True
    # Check if it's very short and likely incomplete
    if len(t) < 10 and not t.endswith((':', '.', '!', '?')):
        return True
    # Check if it's a common incomplete phrase
    incomplete_patterns = [
        r'^to\s+present\s+a\s+proposal\s+for\s+developing\s+the\s+business\s+plan\s+for\s+the\s+ontario$',
        r'^rfp:\s+to\s+develop\s+the\s+ontario\s+digital\s+library\s+business\s+plan$',
        r'^march\s+\d{4}$'
    ]
    for pattern in incomplete_patterns:
        if re.match(pattern, t.lower()):
            return True
    return False

def remove_duplicate_headings(outline):
    """Remove duplicate headings from the outline"""
    seen = set()
    unique_outline = []
    for heading in outline:
        # Create a key based on text and level to identify duplicates
        key = (heading['text'].strip().lower(), heading['level'])
        if key not in seen:
            seen.add(key)
            unique_outline.append(heading)
    return unique_outline

def is_date_or_month_or_number(text):
    t = text.strip().lower()
    # Exclude if only a number (with or without punctuation)
    if re.fullmatch(r'[\d.,/\-]+', t):
        return True
    # Exclude if only a month name
    if t in MONTHS:
        return True
    # Exclude if matches common date patterns
    if re.fullmatch(r'\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?', t):
        return True
    if re.fullmatch(r'\d{4}', t):
        return True
    # Exclude date patterns like "March 21, 2003", "March 2003", etc.
    if re.match(r'^(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+\d{4}$', t):
        return True
    if re.match(r'^(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}$', t):
        return True
    if re.match(r'^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2},?\s+\d{4}$', t):
        return True
    if re.match(r'^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{4}$', t):
        return True
    return False

def clean_text(text):
    """Clean extracted text by fixing common spacing issues"""
    if not text:
        return text
    
    # Fix common spacing issues
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)  # Add space between camelCase
    text = re.sub(r'([A-Z])([A-Z][a-z])', r'\1 \2', text)  # Add space between ALLCAPS and TitleCase
    text = re.sub(r'([a-zA-Z])(\d)', r'\1 \2', text)  # Add space between letters and numbers
    text = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', text)  # Add space between numbers and letters
    
    # Fix bullet points
    text = re.sub(r'•([A-Za-z])', r'• \1', text)  # Add space after bullet
    text = re.sub(r'([a-z])•', r'\1 •', text)  # Add space before bullet
    
    # Fix common punctuation
    text = re.sub(r'([a-zA-Z]):([a-zA-Z])', r'\1: \2', text)  # Add space after colon
    text = re.sub(r'([a-zA-Z]),([a-zA-Z])', r'\1, \2', text)  # Add space after comma
    
    # Clean up multiple spaces
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

def extract_all_text_with_font_tags(pdf_path: Path) -> List[Dict]:
    """Phase 1: Extract ALL text and tag by font size hierarchy without filtering"""
    all_text = []
    
    for page_num, page_layout in enumerate(extract_pages(pdf_path), 1):
        # Get page dimensions
        page_width = page_layout.width
        page_height = page_layout.height
        
        for element in page_layout:
            if isinstance(element, LTImage):
                continue  # Skip images
            if isinstance(element, LTTextBoxHorizontal):
                for line in element:
                    if isinstance(line, LTTextLineHorizontal):
                        # Extract complete text from the line
                        text_parts = []
                        font_names = []
                        font_sizes = []
                        for char in line:
                            if isinstance(char, LTChar):
                                text_parts.append(char.get_text())
                                font_name = char.fontname
                                font_size = char.size
                                # If bold, add +1 to font size
                                if font_name and any(b in font_name for b in ['Bold', 'bold', 'Heavy', 'Black']):
                                    font_size += 1
                                font_names.append(font_name)
                                font_sizes.append(font_size)
                        text = ''.join(text_parts).strip()
                        text = clean_text(text)
                        if not text or len(text.strip()) < 1:
                            continue
                        # Enhanced handling for colon:
                        if ':' in text:
                            colon_index = text.index(':')
                            # Find the character index in the text_parts list
                            char_count = 0
                            split_index = None
                            for idx, part in enumerate(text_parts):
                                char_count += len(part)
                                if char_count > colon_index:
                                    split_index = idx
                                    break
                            # Find the first non-space character after the colon
                            after_colon_idx = split_index + 1 if split_index is not None else None
                            while after_colon_idx is not None and after_colon_idx < len(text_parts) and text_parts[after_colon_idx].isspace():
                                after_colon_idx += 1
                            if split_index is not None and after_colon_idx is not None and after_colon_idx < len(font_names):
                                font_before = font_names[split_index]
                                font_after = font_names[after_colon_idx]
                                size_before = font_sizes[split_index]
                                size_after = font_sizes[after_colon_idx]
                                # If font name or font size differs, only use text before the colon
                                if (font_before != font_after) or (abs(size_before - size_after) > 0.5):
                                    text = text[:colon_index]
                                    font_names = font_names[:split_index+1]
                                    font_sizes = font_sizes[:split_index+1]
                        if font_sizes:
                            avg_font_size = sum(font_sizes) / len(font_sizes)
                            font_counter = Counter(font_names)
                            most_common_font = font_counter.most_common(1)[0][0]
                        else:
                            avg_font_size = None
                            most_common_font = None
                        all_text.append({
                            'text': text,
                            'font_size': avg_font_size,
                            'font_name': most_common_font,
                            'page': page_num,
                            'y0': line.y0,
                            'x0': line.x0,
                            'x1': line.x1,
                            'page_width': page_width,
                            'page_height': page_height,
                        })
    return all_text

def tag_by_font_hierarchy(all_text: List[Dict]) -> List[Dict]:
    """Tag all text by font size hierarchy - largest font = H1, second largest = H2, etc."""
    if not all_text:
        return []
    
    # Get all font sizes
    font_sizes = [item['font_size'] for item in all_text if item['font_size']]
    
    # Group similar font sizes with tolerance
    tolerance = 0.1  # Consider font sizes within 0.1 points as the same
    grouped_sizes = []
    
    for size in font_sizes:
        # Check if this size is close to any existing group
        grouped = False
        for group in grouped_sizes:
            if abs(size - group) <= tolerance:
                grouped = True
                break
        if not grouped:
            grouped_sizes.append(size)
    
    # Sort grouped sizes from largest to smallest
    unique_sizes = sorted(grouped_sizes, reverse=True)
    
    # Create mapping: font_size -> heading_level
    size_to_level = {}
    for i, size in enumerate(unique_sizes):
        size_to_level[size] = f"H{i+1}"
    
    # Tag text items
    tagged_text = []
    for item in all_text:
        if item['font_size']:
            # Find the closest grouped size
            closest_size = None
            min_diff = float('inf')
            for size in unique_sizes:
                diff = abs(item['font_size'] - size)
                if diff <= tolerance and diff < min_diff:
                    min_diff = diff
                    closest_size = size
            
            if closest_size is not None:
                item['level'] = size_to_level[closest_size]
            else:
                item['level'] = "H_body"
        else:
            item['level'] = "H_body"
        
        tagged_text.append(item)
    
    return tagged_text

def is_actual_heading(text: str, level: str, x0: float = None, y0: float = None, page_width: float = None, page_height: float = None, font_name: str = None) -> bool:
    """Phase 2: Decide if tagged text is actually a heading"""
    t = text.strip()

    # Exclude if text is fully enclosed in brackets
    if (t.startswith('(') and t.endswith(')')) or \
       (t.startswith('[') and t.endswith(']')) or \
       (t.startswith('{') and t.endswith('}')):
        return False

    # New check: Exclude if first non-space character is lowercase
    t_no_space = t.lstrip()
    if t_no_space and t_no_space[0].islower():
        return False

    # Skip if it's body text level
    if level == "H_body":
        return False
    
    # 1) If starts with lowercase letter (not a heading) - check this FIRST
    # TEMPORARILY DISABLED for testing
    # if t and len(t.strip()) > 0 and t.strip()[0].islower():
    #     return False
    
    # 2) If contains mostly lowercase letters (not a heading)
    # TEMPORARILY DISABLED for testing
    # if len(t) > 3:
    #     letters = [c for c in t if c.isalpha()]
    #     if len(letters) > 0:
    #         lowercase_count = sum(1 for c in letters[1:] if c.islower())  # Skip first letter
    #         total_letters_after_first = len(letters) - 1
    #         if total_letters_after_first > 0 and lowercase_count / total_letters_after_first > 0.5:
    #             return False
    
    # 3) If looks like a sentence (not a heading)
    if len(t) > 20 and ',' in t and t.count(' ') > 5:
        return False
    
    # 4) ALL CAPS - definitely a heading (override other checks)
    if t.isupper() and len(t) > 2:
        return True
    
    # 5) Underlined - definitely a heading (would need underline detection)
    # This would require additional processing during text extraction
    # For now, we'll skip this as we don't have underline info
    
    # 6) Bold - definitely a heading
    if font_name and any(bold_indicator in font_name.lower() for bold_indicator in ['bold', 'b', 'heavy', 'black']):
        return True
    
    # 7) Italics - not a heading (REMOVED - too strict, filters out valid headings)
    # if font_name and any(italic_indicator in font_name.lower() for italic_indicator in ['italic', 'i', 'oblique']):
    #     return False
    

    
    # 8) Only numbers or digits - not a heading
    if re.fullmatch(r'[\d.,/\-]+', t):
        return False
    
    # 9) Date, month, year, day combinations - not a heading
    if is_date_or_month_or_number(t):
        return False
    
    # 10) Position near the centre - likely a heading
    if x0 is not None and page_width is not None:
        center_x = page_width / 2
        # Check if text is roughly centered (within 30% of center)
        if abs(x0 - center_x) < page_width * 0.3:
            return True
    
    # 11) Above the paragraph - likely a heading
    # This would need comparison with surrounding text positions
    # For now, we'll use a simple heuristic: text in top 30% of page is likely heading
    if y0 is not None and page_height is not None:
        if y0 > page_height * 0.7:  # Top 30% of page
            return True
    
    # 12) More than 10 words - not a heading
    word_count = len(t.split())
    if word_count > 10:
        return False
    
    # Additional checks for heading characteristics
    
    # Skip if too short (less than 2 characters)
    if len(t) < 2:
        return False
    
    # Skip if too long (more than 100 characters) - likely paragraph
    if len(t) > 100:
        return False
    
    # Skip if contains typical non-heading patterns
    if re.match(r'^\d+\.$', t):  # Just a number with period
        return False
    
    # Skip if it's just punctuation or symbols
    if re.fullmatch(r'[^\w\s]+', t):
        return False
    
    # Skip if it's a common non-heading word
    non_heading_words = {'page', 'continued', 'footnote', 'reference', 'appendix', 'index', 'glossary'}
    if t.lower() in non_heading_words:
        return False
    
    # Skip if it's a page number or section number
    if re.match(r'^page\s+\d+$', t.lower()):
        return False
    
    # Skip if it's a copyright notice
    if 'copyright' in t.lower() or '©' in t:
        return False
    
    # Skip if it's a URL or email
    if re.search(r'http[s]?://|www\.|@', t):
        return False
    
    return True

def group_vertical_headings(headings):
    """
    Simple function to group vertically adjacent text with same font properties.
    """
    if not headings:
        return headings
    
    # Sort headings by page, then by y0 (vertical position) in descending order
    sorted_headings = sorted(headings, key=lambda h: (h['page'], -h.get('y0', 0)))
    
    grouped_headings = []
    i = 0
    
    while i < len(sorted_headings):
        current = sorted_headings[i]
        current_font = current.get('font_name')
        current_size = current.get('font_size')
        current_page = current['page']
        current_y0 = current.get('y0', 0)
        current_text = current['text'].strip()
        
        # Find vertically adjacent text with same font properties
        group_texts = [current_text]
        group_y0s = [current_y0]
        group_headings = [current]
        j = i + 1
        
        # Keep looking for more lines that should be grouped
        while j < len(sorted_headings):
            next_heading = sorted_headings[j]
            next_font = next_heading.get('font_name')
            next_size = next_heading.get('font_size')
            next_page = next_heading['page']
            next_y0 = next_heading.get('y0', 0)
            next_text = next_heading['text'].strip()
            
            # SIMPLE LOGIC: Same page + same font + vertically close = GROUP
            if next_page == current_page:
                # Check font similarity (exact match or base font name)
                font_similar = False
                if current_font and next_font:
                    font_similar = (current_font == next_font or 
                                  current_font.split('-')[0] == next_font.split('-')[0])
                elif not current_font and not next_font:
                    font_similar = True
                
                # Check font size similarity (within 0.5 points)
                size_similar = False
                if current_size and next_size:
                    size_similar = abs(current_size - next_size) <= 0.5
                elif not current_size and not next_size:
                    size_similar = True
                
                # Check vertical proximity (within 50 points - very close, like a space apart)
                vertical_distance = abs(current_y0 - next_y0)
                vertically_close = vertical_distance <= 50
                
                # GROUP IF: same font + same size + vertically close
                if font_similar and size_similar and vertically_close:
                    group_texts.append(next_text)
                    group_y0s.append(next_y0)
                    group_headings.append(next_heading)
                    j += 1
                    # Continue looking for more lines (don't break here)
                else:
                    # Check if we should continue with a slightly larger tolerance for multi-line titles
                    # Sometimes lines can be slightly further apart but still part of same heading
                    if len(group_texts) > 1:  # If we already have a group, be more flexible
                        # Increase tolerance to 80 points for continuation
                        vertically_close_extended = vertical_distance <= 80
                        if font_similar and size_similar and vertically_close_extended:
                            group_texts.append(next_text)
                            group_y0s.append(next_y0)
                            group_headings.append(next_heading)
                            j += 1
                            # Continue looking for more lines
                        else:
                            break
                    else:
                        break
            else:
                break
        
        # Create combined heading
        if len(group_texts) > 1:
            # Join multiple lines with space
            combined_text = ' '.join(group_texts)
            # Use the highest y0 (topmost position)
            combined_y0 = max(group_y0s)
            # Use the most common level
            level_counts = {}
            for h in group_headings:
                level = h['level']
                level_counts[level] = level_counts.get(level, 0) + 1
            combined_level = max(level_counts.items(), key=lambda x: x[1])[0]
            
            grouped_heading = {
                'level': combined_level,
                'text': combined_text,
                'page': current_page,
                'y0': combined_y0,
                'font_name': current_font,
                'font_size': current_size
            }
            grouped_headings.append(grouped_heading)
        else:
            # Single heading, keep as is
            grouped_headings.append(current)
        
        i = j
    
    return grouped_headings

def process_pdf(pdf_path: Path, output_path: Path):
    try:
        metadata_title = extract_metadata_title(pdf_path)
        
        # Phase 1: Extract ALL text and tag by font hierarchy
        all_text = extract_all_text_with_font_tags(pdf_path)
        tagged_text = tag_by_font_hierarchy(all_text)
        
        # Phase 2: Apply heading detection criteria to filter headings
        headings = []
        for item in tagged_text:
            if item['level'].startswith('H') and item['level'] != 'H_body':
                if is_actual_heading(
                    item['text'], 
                    item['level'], 
                    item.get('x0'), 
                    item.get('y0'), 
                    item.get('page_width'), 
                    item.get('page_height'),
                    item.get('font_name')
                ):
                    headings.append({
                        'level': item['level'],
                        'text': item['text'].strip(),
                        'page': item['page'],
                        'y0': item.get('y0'),
                        'x0': item.get('x0'),
                        'font_name': item.get('font_name'),
                        'font_size': item.get('font_size')
                    })
        
        # Remove duplicates
        headings = remove_duplicate_headings(headings)
        
        # Group consecutive headings of the same level with same font and size
        headings = group_vertical_headings(headings)
        
        # Count ALL heading types (not just filtered ones)
        all_heading_counts = {}
        for item in tagged_text:
            if item['level'].startswith('H') and item['level'] != 'H_body':
                level = item['level']
                all_heading_counts[level] = all_heading_counts.get(level, 0) + 1

        # Find the breakpoint level (first level with >14 headings)
        max_items_per_level = 14
        breakpoint_level = None
        for i in range(1, 100):
            level = f'H{i}'
            if all_heading_counts.get(level, 0) > max_items_per_level:
                breakpoint_level = level
                break

        # Build filtered_headings according to the clarified logic
        filtered_headings = []
        max_heading_level = 6  # Only include up to H6
        if breakpoint_level:
            breakpoint_index = int(breakpoint_level[1:])
            if breakpoint_index == 1:
                # Special case: H1 is the breakpoint
                for item in headings:
                    if item['level'] == 'H1':
                        if is_actual_heading(
                            item['text'],
                            item['level'],
                            item.get('x0'),
                            item.get('y0'),
                            item.get('page_width'),
                            item.get('page_height'),
                            item.get('font_name')
                        ):
                            filtered_headings.append(item)
                # Exclude all other levels
            else:
                for item in headings:
                    level_index = int(item['level'][1:])
                    if level_index < breakpoint_index and level_index <= max_heading_level:
                        filtered_headings.append(item)
                    # else: skip breakpoint and deeper levels
        else:
            # If no breakpoint, include all headings except the deepest level, but only up to H5
            if all_heading_counts:
                max_level = max(int(l[1:]) for l in all_heading_counts)
                for item in headings:
                    level_index = int(item['level'][1:])
                    if level_index < max_level and level_index <= max_heading_level:
                        filtered_headings.append(item)

        # Clean up headings to only include level, text, and page for output
        cleaned_headings = []
        for heading in filtered_headings:
            cleaned_headings.append({
                'level': heading['level'],
                'text': heading['text'],
                'page': heading['page']
            })
        
        # Count filtered heading types dynamically
        filtered_heading_counts = {}
        for heading in filtered_headings:
            level = heading['level']
            filtered_heading_counts[level] = filtered_heading_counts.get(level, 0) + 1
        
        print(f"Processed {pdf_path.name} -> {output_path.name}")
        
        # Display ALL headings found in ascending order (H1, H2, H3, etc.)
        all_headings_output = []
        for i in range(1, 100):  # Support up to H99
            level = f'H{i}'
            count = all_heading_counts.get(level, 0)
            if count > 0:
                all_headings_output.append(f"{level}={count}")
        
        if all_headings_output:
            print(f"  ALL headings found: {', '.join(all_headings_output)}")
        else:
            print(f"  ALL headings found: None")
        
        # Display filtered headings in order from H1, H2, H3, etc.
        filtered_output = []
        for i in range(1, 100):  # Support up to H99
            level = f'H{i}'
            count = filtered_heading_counts.get(level, 0)
            if count > 0:
                filtered_output.append(f"{level}={count}")
        
        if filtered_output:
            print(f"  Filtered headings: {', '.join(filtered_output)}")
        else:
            print(f"  Filtered headings: None")
        
        # Set the document title
        if metadata_title:
            title = metadata_title
        else:
            # Try first page, then second page for the largest heading
            for page_num in [1, 2]:
                page_headings = [h for h in headings if h['page'] == page_num and h['level'] != 'H_body' and h.get('font_size')]
                if page_headings:
                    largest_heading = max(page_headings, key=lambda h: h['font_size'])
                    title = largest_heading['text']
                    break
            else:
                # Fallback: largest text on first or second page
                for page_num in [1, 2]:
                    page_lines = [l for l in tagged_text if l['page'] == page_num and l['font_size']]
                    if page_lines:
                        largest = max(page_lines, key=lambda l: l['font_size'])
                        title = largest['text']
                        break
                else:
                    title = "Untitled"

        result = {
            'title': title,
            'outline': cleaned_headings
        }
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except PDFSyntaxError:
        print(f"Failed to process {pdf_path.name}: PDFSyntaxError")
    except Exception as e:
        print(f"Failed to process {pdf_path.name}: {e}")

def main():
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pdf_files = list(INPUT_DIR.glob("*.pdf"))
    if not pdf_files:
        print("No PDF files found in input directory.")
        return
    for pdf_file in pdf_files:
        output_file = OUTPUT_DIR / f"{pdf_file.stem}.json"
        process_pdf(pdf_file, output_file)

if __name__ == "__main__":
    main() 