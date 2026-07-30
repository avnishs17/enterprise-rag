import logfire
from unstructured.partition.auto import partition


def parse_office(file_path: str):
    """
    Parse an Office documents (.docx , .pptx) using Unstructured  library.
    Unlike pdfs these formats are structured and lightweight so they are processed locally.
    return the parsed clean text.
    """

    with logfire.span("OFFICE DOCUMENT parsing", filename=file_path):
        try:
            # Unstructured automatically detects the file type
            elements = partition(filename=file_path)

            full_text = "\n".join([str(e) for e in elements])

            if not full_text.strip():
                logfire.warning(f"Unstructured returned empty text for {file_path}")
            else:
                logfire.info(f"Successfully parsed {len(full_text)} characters from {file_path}")

            return full_text

        except Exception as e:
            logfire.error(f"Failed to parse Office document: {e}")
            raise e
