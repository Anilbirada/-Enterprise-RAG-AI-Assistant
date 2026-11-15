import re
import unicodedata
from collections import Counter
from typing import List, Tuple


class TextNormalizer:
    """Robust text normalization, character cleaning, and header/footer deduplication."""

    @staticmethod
    def normalize_unicode(text: str) -> str:
        """Applies Unicode NFKC normalization to standardize ligatures, quotes, and symbols."""
        if not text:
            return ""
        # NFKC decomposes combined characters and standardizes compatibility characters
        normalized = unicodedata.normalize("NFKC", text)
        # Standardize curly quotes and whitespace for consistent tokenization and search
        normalized = (
            normalized.replace("\u201c", '"')
            .replace("\u201d", '"')
            .replace("\u2018", "'")
            .replace("\u2019", "'")
            .replace("\xa0", " ")
            .replace("\u200b", "")
        )
        return normalized

    @staticmethod
    def strip_control_characters(text: str) -> str:
        """Removes non-printable ASCII control characters while preserving newlines and tabs."""
        if not text:
            return ""
        # Keep \t (0x09), \n (0x0A), \r (0x0D)
        return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)

    @classmethod
    def clean_text(cls, text: str) -> str:
        """Executes full standard cleaning pipeline on a raw text string."""
        if not text:
            return ""
        
        # 1. Normalize unicode
        text = cls.normalize_unicode(text)

        # 2. Strip non-printable control characters
        text = cls.strip_control_characters(text)

        # 3. Standardize newline separators
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # 4. Collapse multiple horizontal whitespace characters (spaces, tabs) into single spaces
        text = re.sub(r"[ \t]+", " ", text)

        # 5. Strip trailing and leading whitespace on each line
        lines = [line.strip() for line in text.split("\n")]
        text = "\n".join(lines)

        # 6. Collapse 3+ consecutive newlines into 2 (preserving paragraph boundaries)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    @classmethod
    def format_markdown_table(cls, headers: List[str], rows: List[List[str]]) -> str:
        """Formats 2D table data into a clean, standard GitHub Flavored Markdown table."""
        if not headers and not rows:
            return ""

        # Determine column count
        col_count = len(headers) if headers else (max(len(r) for r in rows) if rows else 0)
        if col_count == 0:
            return ""

        # Pad or generate headers if absent
        if not headers:
            headers = [f"Column {i + 1}" for i in range(col_count)]
        elif len(headers) < col_count:
            headers = headers + [f"Column {i + 1}" for i in range(len(headers), col_count)]

        # Clean cell contents (replace internal newlines and pipe characters)
        def _clean_cell(val: str) -> str:
            val_clean = str(val or "").strip().replace("\n", " ").replace("|", "\\|")
            return val_clean if val_clean else "-"

        clean_headers = [_clean_cell(h) for h in headers[:col_count]]
        clean_rows = []
        for row in rows:
            cleaned_row = [_clean_cell(row[i] if i < len(row) else "") for i in range(col_count)]
            clean_rows.append(cleaned_row)

        # Construct markdown representation
        header_line = "| " + " | ".join(clean_headers) + " |"
        separator_line = "| " + " | ".join(["---"] * col_count) + " |"
        row_lines = ["| " + " | ".join(r) + " |" for r in clean_rows]

        return "\n".join([header_line, separator_line] + row_lines)

    @classmethod
    def deduplicate_headers_footers(cls, page_texts: List[str]) -> List[str]:
        """Detects and strips repetitive running headers and footers across document pages.
        
        Identifies lines appearing on >= 70% of pages (at the top 2 or bottom 2 lines)
        when the document contains at least 3 pages.
        """
        if len(page_texts) < 3:
            return page_texts

        top_lines = []
        bottom_lines = []
        split_pages = [p.split("\n") for p in page_texts]

        for lines in split_pages:
            non_empty = [l.strip() for l in lines if l.strip()]
            if len(non_empty) >= 1:
                top_lines.append(non_empty[0])
            if len(non_empty) >= 2:
                top_lines.append(non_empty[1])
            if len(non_empty) >= 1:
                bottom_lines.append(non_empty[-1])
            if len(non_empty) >= 2:
                bottom_lines.append(non_empty[-2])

        total_pages = len(page_texts)
        threshold = total_pages * 0.70

        # Find repetitive headers and footers
        repeated_headers = {
            line for line, count in Counter(top_lines).items()
            if count >= threshold and len(line) > 3
        }
        repeated_footers = {
            line for line, count in Counter(bottom_lines).items()
            if count >= threshold and len(line) > 3
        }

        # Also detect standard page number patterns like "Page X of Y" or "- X -"
        page_num_regex = re.compile(
            r"^(page\s+\d+(\s+of\s+\d+)?|\d+\s*/\s*\d+|-\s*\d+\s*-|\d+)$",
            re.IGNORECASE,
        )

        cleaned_pages = []
        for lines in split_pages:
            filtered_lines = []
            for i, line in enumerate(lines):
                stripped = line.strip()
                # Skip if matches identified recurring header/footer
                if stripped in repeated_headers or stripped in repeated_footers:
                    continue
                # Skip if at page perimeter and matches page numbering
                if (i <= 2 or i >= len(lines) - 3) and page_num_regex.match(stripped):
                    continue
                filtered_lines.append(line)

            cleaned_pages.append("\n".join(filtered_lines))

        return cleaned_pages
