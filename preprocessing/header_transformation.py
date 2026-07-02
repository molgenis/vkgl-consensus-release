import shutil
from pathlib import Path
from typing import List

from utils.configuration import Configuration
from utils.printer import Printer
from utils.report import ReleaseError, ReleaseWarning


class TransformHeaders:
    """
    Replace lab system specific column names with the general VKGL consensus ones
    """

    def __init__(self, config: Configuration, lab: str, warnings: List[ReleaseWarning]):
        self.config = config
        self.lab = lab
        self.lab_system = config.labs[lab]["labSystem"]
        self.printer = Printer()
        self.warnings = warnings

    def add_header(self, file: Path):
        try:
            with open(f"temp_header{file.suffix}", "w", encoding="utf-8") as outfile:
                with open(file, "r", encoding="utf-8") as infile:
                    self.printer.print(
                        f"📝 Add missing header to {file.name}", indent=1
                    )
                    header = f"{self.config.labfile_headers[self.lab_system]}\n"
                    outfile.write(header)
                    shutil.copyfileobj(infile, outfile)

            shutil.move(f"temp_header{file.suffix}", file)
        except Exception as e:
            raise ReleaseError(f"Something went wrong while adding the header: {e}")

    def cleanup_header(self, file: Path):
        try:
            with open(f"temp_header{file.suffix}", "w", encoding="utf-8") as outfile:
                with open(file, "r", encoding="utf-8", newline="") as infile:
                    self.printer.print(
                        f"🧼 Clean up invalid characters in header in " f"{file.name}",
                        indent=1,
                    )
                    delimiter = "\t"
                    if file.suffix in [".csv"]:
                        delimiter = ","
                    cleaned_header = list()
                    # Remove invalid (for EMX2) column characters
                    for column in next(infile).split(delimiter):
                        for to_replace in ["(", ")", "%"]:
                            column = column.replace(to_replace, "")
                        cleaned_header.append(column.strip())

                    outfile.write(f"{delimiter.join(cleaned_header)}\n")
                    shutil.copyfileobj(infile, outfile)

            shutil.move(f"temp_header{file.suffix}", file)
        except Exception as e:
            raise ReleaseError(
                f"Something went wrong while cleaning up the header: {e}"
            )

    def replace_header(self, file: Path):
        try:
            with open(f"temp_header{file.suffix}", "w", encoding="utf-8") as outfile:
                with open(file, "r", encoding="utf-8") as infile:
                    self.printer.print(f"📝 Replace header in {file.name}", indent=1)
                    header = f"{self.rewrite_header(next(infile))}\n"
                    outfile.write(header)
                    shutil.copyfileobj(infile, outfile)

            shutil.move(f"temp_header{file.suffix}", file)
        except Exception as e:
            raise ReleaseError(f"Something went wrong while replacing the header: {e}")

    def rewrite_header(self, old_header: str):
        new_header = []
        for column in old_header.split("\t"):
            try:
                new_header.append(
                    self.config.labfile2vkgl_columns[self.lab_system][column.strip()]
                )
            except KeyError:
                if column != "id":
                    self._warn(f"No mapping found for column {column}")
                new_header.append(column)

        return "\t".join(new_header)

    def _warn(self, message: str):
        warning = ReleaseWarning(message)
        self.printer.print_warning(warning, indent=2)
        self.warnings.append(warning)
