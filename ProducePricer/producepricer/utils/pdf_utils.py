def extract_pdf_text(file_path: str) -> str:
    import pdfplumber
    text_parts = []
    try:
        with pdfplumber.open(file_path) as pdf:
            # Even for single-page PDFs, we need to limit extraction time
            for page in pdf.pages:
                extracted_text = page.extract_text() or ""
                # Clean the text to remove potentially problematic characters
                if extracted_text:
                    # Remove null bytes and other control characters that might cause issues
                    cleaned_text = ''.join(char for char in extracted_text if char.isprintable() or char in '\n\t\r')
                    text_parts.append(cleaned_text)

        result = "\n".join(text_parts)
        # Final cleanup to ensure we don't have any characters that could break JSON
        result = result.replace('\x00', '').replace('\ufffd', '')  # Remove null bytes and replacement chars
        return result
    except Exception as e:
        print(f"PDF read error: {e}")
        return ""  # Return empty string instead of None
