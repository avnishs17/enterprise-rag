import logfire
from bs4 import BeautifulSoup

def parse_html(file_path: str):
    """
    Parse an HTML file using BeautifulSoup and
    return the parsed clean text.
    """
    with logfire.span("HTML Parsing", filename=file_path):
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            soup = BeautifulSoup(content, "html.parser")

            # 1. Remove junk such as scripts, styles, and metadata

            for script in soup(["script", "style", "meta", "noscript"]):
                script.decompose()

            # 2. Extract the text
            text = soup.get_text(separator="\n")

            # 3. Clean whitespace [ collapase multiple newlines]

            lines = (line.strip() for line in text.splitlines())
            chunks = (phase.strip() for line in lines for phase in line.split(" "))
            cleaned_text = "\n".join(chunk for chunk in chunks if chunk)
            return cleaned_text
        except Exception as e:
            logfire.error(f"Failed to parse HTML: {e}")
            raise e
