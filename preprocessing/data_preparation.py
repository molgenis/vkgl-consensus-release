import csv
import shutil
from pathlib import Path
from typing import List, cast

from utils.configuration import Configuration
from utils.printer import Printer
from utils.report import ReleaseError, ReleaseWarning
from utils.utils import get_hash

from .data_cleaning import DataCleaner
from .header_transformation import TransformHeaders


class DataPreparer:
    """
    - Add variant IDs
    - Align classification
    """

    def __init__(
        self,
        config: Configuration,
        lab: str,
        warnings: List[ReleaseWarning],
        processing_feedback: List[dict],
    ):
        self.config = config
        self.lab = lab
        self.lab_system = config.labs[lab]["labSystem"]
        self.printer = Printer()
        self.processing_feedback = processing_feedback
        self.warnings = warnings
        Path(f"{config.cleaned_folder}/{lab}").mkdir(parents=True, exist_ok=True)
        Path(f"{config.processed_folder}/{lab}").mkdir(parents=True, exist_ok=True)

    def prepare_data(self):
        files = self._get_files_from_folder(f"{self.config.raw_data_folder}/{self.lab}")
        header_transformation = TransformHeaders(self.config, self.lab, self.warnings)
        try:
            for file in files:
                if self.config.labs[self.lab]["missingHeader"]:
                    header_transformation.add_header(file)
                self.add_variant_id(file)
                DataCleaner(
                    self.config, self.lab, self.warnings, self.processing_feedback
                ).clean_data(file)
            files = self._get_files_from_folder(
                f"{self.config.cleaned_folder}/{self.lab}"
            )
            for file in files:
                header_transformation.replace_header(file)
                header_transformation.cleanup_header(file)
                self.align_classifications(file)
            files = self._get_files_from_folder(
                f"{self.config.processed_folder}/{self.lab}", [".csv"]
            )
            for file in files:
                header_transformation.cleanup_header(file)
        except ReleaseError as e:
            raise ReleaseError(e)

    def add_variant_id(self, file):
        """
        File is a tsv or txt file from the raw lab data folder
        :param file: raw lab data file
        """
        self.printer.print(f"🆔 Add variant IDs to {file.name}", indent=1)
        try:
            with open(file, "r", encoding="utf-8") as infile:
                reader = csv.DictReader(infile, delimiter="\t")
                header = ["id"] + cast(list, reader.fieldnames)
                with open(f"temp_file{file.suffix}", "w", encoding="utf-8") as outfile:
                    writer = csv.DictWriter(outfile, fieldnames=header, delimiter="\t")
                    writer.writeheader()
                    for row in reader:
                        row: dict[str, str]  # type hint to prevent warnings
                        columns = self.config.vkgl2labfile_columns[self.lab_system]
                        if "variantType" not in columns:
                            columns["variantType"] = "variantType"
                        # Raw Lab data ID includes more columns than ID in the
                        # consensus, as in raw data some info is missing and all
                        # unique raw data are included in the database
                        if "hgvs" in columns:
                            _id = row.get(columns["hgvs"], "").strip()
                        else:
                            _id = (
                                f"{row.get(columns['chromosome'], '').strip()}_"
                                f"{row.get(columns['start'], '').strip()}_"
                                f"{row.get(columns['stop'], '').strip()}_"
                                f"{row.get(columns['ref'], '').strip()}_"
                                f"{row.get(columns['alt'], '').strip()}_"
                                f"{row.get(columns['variantType'], '').strip()}_"
                                f"{row.get(columns['transcript'], '').strip()}_"
                                f"{row.get(columns.get('gene', ''), '').strip()}"
                            )

                        row["id"] = f"{self.lab.upper()}_" + get_hash(_id)[0:10]
                        writer.writerow(row)

            shutil.move(f"temp_file{file.suffix}", file)

        except KeyError as e:
            raise ReleaseError(f"Missing key {e} while adding variant IDs")

        except Exception as e:
            raise ReleaseError(f"Something went wrong while adding IDs: {e}")

    def align_classifications(self, file):
        self.printer.print(
            f"🔄 Generalise variant classifications in {file.name}", indent=1
        )
        try:
            with open(file, "r", encoding="utf-8") as infile:
                reader = csv.DictReader(infile, delimiter="\t")
                header = cast(list, reader.fieldnames)
                with open(f"temp_file{file.suffix}", "w", encoding="utf-8") as outfile:
                    writer = csv.DictWriter(outfile, fieldnames=header, delimiter="\t")
                    writer.writeheader()
                    for row in reader:
                        row: dict[str, str]  # type hint to prevent warnings
                        mapping = self.config.lab2vkgl_classifications[self.lab_system]
                        if row["classification"]:
                            row["classification"] = mapping[row["classification"]]

                        writer.writerow(row)

            shutil.move(f"temp_file{file.suffix}", file)

        except KeyError as e:
            raise ReleaseError(f"Missing key {e} while aligning the classifications")

        except Exception as e:
            raise ReleaseError(
                f"Something went wrong while aligning the " f"classifications: {e}"
            )

    def _get_files_from_folder(self, folder, suffixes: List[str] = None):
        if suffixes is None:
            suffixes = [".tsv", ".txt"]
        files = [
            f
            for f in sorted(Path(folder).iterdir(), key=lambda x: x.name)
            if f.suffix in suffixes and f.is_file()
        ]
        if not files:
            self._warn(f"No tsv of txt file found in {folder}")
            return None
        return files

    def _warn(self, message: str):
        warning = ReleaseWarning(message)
        self.printer.print_warning(warning, indent=2)
        self.warnings.append(warning)
