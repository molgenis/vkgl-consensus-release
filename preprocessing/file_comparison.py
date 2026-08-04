from pathlib import Path
from typing import List

import pandas as pd

from utils.printer import Printer
from utils.report import ReleaseError, ReleaseReport, ReleaseWarning
from utils.utils import extract_date


class FileComparing:
    """
    Compare files and detect and process only new or updated data
    """

    def __init__(
        self,
        lab: str,
        lab_name: str,
        input_folder: str,
        report: ReleaseReport,
        warnings: List[ReleaseWarning],
        output_folder: str = None,
    ):
        self.input_folder = Path(input_folder)
        self.lab = lab
        self.lab_name = lab_name
        if output_folder:
            self.output_folder = Path(output_folder)
        self.printer = Printer()
        self.report = report
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
        mutations = new_data - old_data
        if not mutations:
            self._warn("No new or updated variants available")
        else:
            self.printer.print(
                f"🆕 {len(mutations)} new or updated variants found", indent=1
            )
            self.check_mutations(old_file, new_file, mutations)

            self.save_new_rows(self.ingest(new_file).splitlines()[0], mutations)

    def check_mutations(self, old: Path, new: Path, mutations):
        df_old = pd.read_csv(old, dtype=str, delimiter="\t")
        df_new = pd.read_csv(new, dtype=str, delimiter="\t")

        mutated_ids = [variant.split("\t")[0] for variant in list(mutations)]

        df_new_variants = df_new[~df_new["id"].isin(df_old["id"])]
        self.report.update_summary(self.lab_name, {"new": len(df_new_variants)})

        df_updates = df_old[df_old["id"].isin(mutated_ids)]
        self.report.update_summary(self.lab_name, {"updated": len(df_updates)})

        self.printer.print("🔍 Check for deleted variants", indent=1)
        df_deletes = df_old[~df_old["id"].isin(df_new["id"])]

        if not df_deletes.empty:
            self._warn(f"{len(df_deletes)} deleted variants found")
            df_deletes.to_csv(
                f"{self.output_folder}/deleted_variants.tsv", sep="\t", index=False
            )
        else:
            self.printer.print("📌 No deleted variants found", indent=1)

        self.report.update_summary(self.lab_name, {"deleted": len(df_deletes)})

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
