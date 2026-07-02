from pathlib import Path
from typing import List

import pandas as pd

from utils.printer import Printer
from utils.report import ReleaseError, ReleaseWarning
from utils.utils import extract_date


class FileComparing:
    """
    Compare files and detect and process only new or updated data
    """

    def __init__(
        self,
        lab: str,
        input_folder: str,
        warnings: List[ReleaseWarning],
        output_folder: str = None,
    ):
        self.input_folder = Path(input_folder)
        if output_folder:
            self.output_folder = Path(output_folder)
        self.printer = Printer()
        self.lab = lab
        self.warnings = warnings

    def list_and_sort_files(self, desc: bool = False):
        files = [
            f
            for f in self.input_folder.iterdir()
            if f.suffix in [".tsv", ".txt"] and f.is_file()
        ]

        files.sort(key=extract_date, reverse=desc)
        return files

    @staticmethod
    def ingest(file_path: Path):
        with file_path.open("r") as f:
            return f.read()

    def compare_files(self):
        files = self.list_and_sort_files()
        if len(files) != 2:
            raise ReleaseError(
                f"{len(files)} file(s) found to compare, while two "
                f"are expected. Check {self.input_folder}"
            )
        old_file, new_file = files[-2], files[-1]
        old_data = set(self.ingest(old_file).splitlines())
        new_data = set(self.ingest(new_file).splitlines())
        new_rows = new_data - old_data
        if not new_rows:
            self._warn("No new variants available")
        else:
            self.printer.print(
                f"🆕 {len(new_rows)} new or updated variants found", indent=1
            )

            self.save_new_rows(self.ingest(new_file).splitlines()[0], new_rows)

        self.check4deleted_data(old_file, new_file)

    def check4deleted_data(self, old: Path, new: Path):
        self.printer.print("🔍 Check for deleted variants", indent=1)
        df_old = pd.read_csv(old, dtype=str, delimiter="\t")
        df_new = pd.read_csv(new, dtype=str, delimiter="\t")

        df_deletes = df_old[~df_old["id"].isin(df_new["id"])]

        if not df_deletes.empty:
            self._warn(f"{len(df_deletes)} deleted variants found")
            df_deletes.to_csv(
                f"{self.output_folder}/deleted_variants.tsv", sep="\t", index=False
            )
        else:
            self.printer.print("📌 No deleted variants found", indent=1)

    def save_new_rows(self, header: str, new_rows: set[str]):
        self.output_folder.mkdir(parents=True, exist_ok=True)
        output_file = self.output_folder / "new_variants.tsv"
        with output_file.open("w") as f:
            f.write(header + "\n")
            for row in new_rows:
                f.write(row + "\n")

    def _warn(self, message: str):
        warning = ReleaseWarning(message)
        self.printer.print_warning(warning, indent=2)
        self.warnings.append(warning)
