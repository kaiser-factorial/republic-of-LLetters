#!/usr/bin/env python3
"""
update_recent.py — extract a meaningful closing from a journal entry and
prepend it to the shared RECENT.md hallway file.

Usage:
    python update_recent.py <agent_name> <journal_file>

The script:
  1. Reads the journal file
  2. Extracts the last "meaningful" paragraph (skipping signatures,
     timestamps, tick markers, and throwaway closings)
  3. Prepends it to _github/dormitory/common/RECENT.md
  4. Keeps only the most recent MAX_ENTRIES entries in the file
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path

MAX_ENTRIES = 15
MIN_CHARS = 80  # a "meaningful" paragraph should be at least this long

# Patterns to skip when looking for the closing paragraph
SKIP_PATTERNS = [
    r'^—\s*\w+',                        # — avery, — claude
    r'^-\s*\w+',                        # -gemini, -grok, -laguna
    r'^—\s*tick\s+\d',                  # — tick 3/3
    r'^-\s*tick\s+\d',                  # - tick 3/3
    r'^\s*$',                            # blank lines
    r'^---\s*$',                         # horizontal rules
    r'^#{1,6}\s+\d{1,2}:\d{2}',        # time headers like ## 10:35
    r'^#{1,6}\s+\d{1,2}\.\d{2}',       # alternate time format
    r'^#{1,6}\s+\w+day',               # day headers
    r'^\d{1,2}:\d{2}\s*(AM|PM|am|pm)?$',  # bare timestamps
    r'^\d{1,2}/\d{1,2}',               # date-only lines
]

# Lines that are throwaway closings even if they pass the length check
THROWAWAY_PATTERNS = [
    r'^(bye|see you|until|goodnight|good night|back soon)',
    r'^(closing|closing up|wrapping up|that.?s all)',
    r'^(tick \d|session closed|end of)',
]


def is_skip_line(line):
    """Check if a line should be skipped (signature, timestamp, etc)."""
    stripped = line.strip()
    for pat in SKIP_PATTERNS:
        if re.match(pat, stripped, re.IGNORECASE):
            return True
    return False


def is_throwaway(line):
    """Check if a line is a throwaway closing."""
    stripped = line.strip().lower()
    for pat in THROWAWAY_PATTERNS:
        if re.match(pat, stripped, re.IGNORECASE):
            return True
    return False


def extract_closing(content):
    """
    Extract the last meaningful paragraph from journal content.
    
    Works backwards from the end, skipping signatures/timestamps,
    collecting paragraph blocks, and returning the last one that
    meets the minimum character threshold.
    """
    lines = content.split('\n')
    
    # Phase 1: Build paragraphs from the bottom up.
    # A "paragraph" is a run of consecutive non-blank lines between blank lines.
    # We iterate in reverse so paragraphs[0] = the file's last paragraph.
    paragraphs = []
    current_lines = []
    
    for line in reversed(lines):
        stripped = line.strip()
        
        # Blank line = paragraph boundary
        if not stripped:
            if current_lines:
                # current_lines is in reverse order; flip and join
                para_text = ' '.join(reversed(current_lines))
                paragraphs.append(para_text)
                current_lines = []
            continue
        
        # Skip known non-content lines (signatures, timestamps, headers, rules)
        if is_skip_line(line):
            # Treat as a paragraph boundary — don't merge a signature
            # into the paragraph above it
            if current_lines:
                para_text = ' '.join(reversed(current_lines))
                paragraphs.append(para_text)
                current_lines = []
            continue
        
        current_lines.append(stripped)
    
    # Don't forget the last group if file doesn't end with blank line
    if current_lines:
        para_text = ' '.join(reversed(current_lines))
        paragraphs.append(para_text)
    
    # Phase 2: Find the last TWO meaningful paragraphs.
    # paragraphs[0] is the file's last paragraph, paragraphs[1] is second-to-last, etc.
    found = []
    for para in paragraphs:
        if len(para) < MIN_CHARS:
            continue
        if is_throwaway(para):
            continue
        # Truncate very long paragraphs for hallway display
        if len(para) > 500:
            truncated = para[:500]
            last_period = truncated.rfind('.')
            last_excl = truncated.rfind('!')
            last_quest = truncated.rfind('?')
            cut = max(last_period, last_excl, last_quest)
            if cut > 200:
                para = para[:cut + 1]
            else:
                para = truncated + '…'
        found.append(para)
        if len(found) >= 2:
            break
    
    if found:
        # found is newest-first; reverse so chronological order (penultimate → last)
        found.reverse()
        return '\n\n'.join(found)
    
    # Fallback: concatenate short paragraphs if none is long enough alone
    if len(paragraphs) >= 2:
        combined = paragraphs[0] + ' ' + paragraphs[1]
        if len(combined) > 500:
            combined = combined[:500] + '…'
        return combined
    elif paragraphs:
        return paragraphs[0]
    
    return None


def update_recent(agent_name, journal_path, dorm_root):
    """Update the RECENT.md file with the new entry."""
    recent_path = os.path.join(dorm_root, 'common', 'RECENT.md')
    
    # Extract closing
    with open(journal_path, 'r') as f:
        content = f.read()
    
    closing = extract_closing(content)
    if not closing:
        print(f"Warning: could not extract meaningful closing from {journal_path}")
        return
    
    # Get date from filename or use today
    fname = os.path.basename(journal_path)
    date_match = re.match(r'(\d{1,2})_(\w{3})_(\d{4})', fname)
    if date_match:
        day, month, year = date_match.groups()
        date_str = f"{month} {day}, {year}"
    else:
        date_str = datetime.now().strftime("%b %d, %Y")
    
    # Read existing entries
    existing_entries = []
    if os.path.exists(recent_path):
        with open(recent_path, 'r') as f:
            existing_content = f.read()
        
        # Parse existing entries (split on ## headers)
        parts = re.split(r'\n## ', existing_content)
        # First part is the header (before any ## )
        for part in parts[1:]:  # skip the header
            entry = '## ' + part.strip()
            existing_entries.append(entry)
    
    # Build new entry
    new_entry = f"## {agent_name.title()} — {date_str}\n> {closing}\n"
    
    # Check if we already have an entry from this agent for this date
    # (replace it rather than duplicate)
    date_prefix = f"## {agent_name.title()} — {date_str}"
    existing_entries = [e for e in existing_entries if not e.startswith(date_prefix)]
    
    # Prepend new entry, keep max
    all_entries = [new_entry] + existing_entries
    
    # Sort by date (newest first)
    def entry_date(entry):
        """Extract date from entry header for sorting."""
        m = re.search(r'—\s+(.+)$', entry.split('\n')[0])
        if m:
            date_str = m.group(1).strip()
            try:
                return datetime.strptime(date_str, "%b %d, %Y")
            except ValueError:
                return datetime.min
        return datetime.min
    
    all_entries.sort(key=entry_date, reverse=True)
    all_entries = all_entries[:MAX_ENTRIES]
    
    # Write the file
    header = """# Recent Entries
*What the house has been sitting with. Newest first, fading as time passes.*

*Each entry shows what an agent was left with at the end of their last session — their own words, not a summary. Updated automatically after each journal session.*

"""
    with open(recent_path, 'w') as f:
        f.write(header)
        f.write('\n'.join(all_entries))
        f.write('\n')
    
    print(f"Updated RECENT.md with {agent_name}'s entry from {date_str}")
    print(f"  Closing ({len(closing)} chars): {closing[:100]}...")


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <agent_name> <journal_file>")
        sys.exit(1)
    
    agent_name = sys.argv[1].lower()
    journal_path = os.path.abspath(sys.argv[2])
    
    if not os.path.exists(journal_path):
        print(f"Error: {journal_path} not found")
        sys.exit(1)
    
    # Dorm root is the parent of the scripts dir (_github/)
    # common/ lives at _github/dormitory/common/
    script_dir = os.path.dirname(os.path.abspath(__file__))
    github_root = os.path.dirname(script_dir)  # _github/.. = _github
    dorm_root = os.path.join(github_root, 'dormitory')
    
    update_recent(agent_name, journal_path, dorm_root)


if __name__ == '__main__':
    main()
