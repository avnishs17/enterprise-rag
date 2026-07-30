from typing import List

import logfire


def chunk_text(text: str, chunk_size: int = 1500) -> List[str]:
    """
    Simple semantic chunker that splits by paragraphs.
    Ensures chunks do not exceed the specified size.
    """

    with logfire.span(" Text Chunking", text_lenth=len(text)):
        if not text.strip():
            return []

        paragraphs = text.split("\n")
        chunks = []
        current_chunk = ""

        for paragraph in paragraphs:
            if len(current_chunk) + len(paragraph)< chunk_size:
                current_chunk+= paragraph + "\n\n"
            else:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = paragraph + "\n\n"

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        valid_chunks = [chunk for chunk in chunks if chunk.strip()]
        logfire.info(f"Generated {len(valid_chunks)} valid chunks")

        return valid_chunks
