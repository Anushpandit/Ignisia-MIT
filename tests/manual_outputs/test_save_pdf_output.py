from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from parser import parse_document, save_parsed_markdown


def main() -> None:
    project_root = ROOT_DIR
    input_file = project_root / "examples" / "sample-report.pdf"
    output_file = project_root / "data" / "sample-report.md"

    parsed_document = parse_document(input_file)
    saved_path = save_parsed_markdown(parsed_document, output_file)

    print(f"Parsed file: {input_file}")
    print(f"Saved output: {saved_path}")


if __name__ == "__main__":
    main()
