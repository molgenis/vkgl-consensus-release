import csv
from collections import Counter
from datetime import datetime
from typing import List, cast

from utils.configuration import Configuration
from utils.printer import Printer
from utils.report import ReleaseError, ReleaseWarning
from utils.utils import extract_date


class DataCleaner:
    """
    Reads in a raw lab data file from the raw lab data folder including variant IDs
    - Removes duplicates
    - Checks and removes opposite classifications within lab
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

    def clean_data(self, file):
        self.printer.print(f"🧹 Clean up {file.name}", indent=1)
        classification = self.config.vkgl2labfile_columns[self.lab_system][
            "classification"
        ]
        checked_data = list()
        cleaned_data = list()
        try:
            file_date = extract_date(file).date()
            with open(file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter="\t")
                header = cast(list, reader.fieldnames)
                variants = list(reader)

            variants = self._remove_explicit_missing_values(variants)
            all_data = self._get_rows_as_tuple(variants, header, "labUploadDate")

            counts = Counter(all_data)
            self.printer.print("🗑️ Remove duplicates", indent=2)
            deduplicated = self._remove_duplicates(all_data)
            if len(all_data) != len(deduplicated):
                self._warn(
                    f"{len(all_data) - len(deduplicated)} duplicate variant(s) found"
                )
            opposites = list()
            if deduplicated:
                opposites = self._check_opposites_within_lab(deduplicated)
                if opposites:
                    self._warn(
                        f"{len(opposites)} opposite classification(s) within "
                        f"this lab found"
                    )

            checked = set()
            cleaned = set()
            no_classification = []
            for variant in variants:
                check_ok = True
                key = self._get_rows_as_tuple([variant], header, "labUploadDate")[0]

                if not variant[classification]:
                    no_classification.append(variant["id"])
                    feedback = {
                        self.lab: variant["id"],
                        "lab": self.lab,
                        "processingStep": "preprocessing",
                        "feedback": "Variant has no classification",
                        "processingDate": datetime.today().strftime("%Y-%m-%d"),
                    }
                    if feedback not in self.processing_feedback:
                        self.processing_feedback.append(feedback)
                    check_ok = False
                if variant["id"] in opposites:
                    variant["id"] = (
                        f"{variant['id']}_"
                        f"{variant[classification].replace(' ', '_')}"
                    )
                    feedback = {
                        self.lab: variant["id"],
                        "lab": self.lab,
                        "processingStep": "preprocessing",
                        "feedback": "Variant has opposite classifications "
                        "within the lab",
                        "processingDate": datetime.today().strftime("%Y-%m-%d"),
                    }
                    if feedback not in self.processing_feedback:
                        self.processing_feedback.append(feedback)
                    check_ok = False

                if check_ok:
                    if key not in cleaned:
                        cleaned_data.append(variant)
                        cleaned.add(key)

                if counts[key] > 1:
                    feedback = {
                        self.lab: variant["id"],
                        "lab": self.lab,
                        "processingStep": "preprocessing",
                        "feedback": f"Variant appears {counts[key]} times "
                        f"in the raw data file",
                        "processingDate": datetime.today().strftime("%Y-%m-%d"),
                    }
                    if feedback not in self.processing_feedback:
                        self.processing_feedback.append(feedback)
                if key not in checked:
                    checked_data.append(variant)
                    checked.add(key)

            self._write_checked_data(header, checked_data)
            self._write_cleaned_data(header, file_date, cleaned_data)

            self.printer.print(
                "👀 Check for variants without a classification", indent=2
            )
            if len(no_classification) > 0:
                self._warn(
                    f"{len(set(no_classification))} variant(s) found without a "
                    f"classification"
                )

        except Exception as e:
            raise ReleaseError(f"Something went wrong while cleaning up the data: {e}")

    @staticmethod
    def _remove_duplicates(data: List[tuple]):
        unique_data = set()
        for row in data:
            if row not in unique_data:
                unique_data.add(row)
        return unique_data

    def _remove_explicit_missing_values(self, data: List[dict]):
        self.printer.print("🧼 Check for and remove explicit missing values", indent=2)
        found = False
        for row in data:
            for k, v in row.items():
                if v == "None":
                    row[k] = ""
                    found = True
        if found:
            self._warn("File contained explicit missing values")
        else:
            self.printer.print("✅ No explicit missing values found", indent=3)
        return data

    def _check_opposites_within_lab(self, data):
        self.printer.print("👀 Check for opposite classifications", indent=2)
        opposites = list()
        classification = self.config.vkgl2labfile_columns[self.lab_system][
            "classification"
        ]
        headers = [k for k, v in next(iter(data)) if k != classification]
        excl_classification = [
            tuple((key, dict(row)[key]) for key in headers) for row in data
        ]
        variant_classification_counts = Counter(excl_classification)
        for row in variant_classification_counts:
            if variant_classification_counts[row] > 1:
                opposites.append(dict(row)["id"])
        return opposites

    def _get_rows_as_tuple(self, data, columns, exclude: str):
        if exclude in self.config.vkgl2labfile_columns[self.lab_system]:
            return [
                tuple(
                    (key, row[key])
                    for key in columns
                    if key != self.config.vkgl2labfile_columns[self.lab_system][exclude]
                )
                for row in data
            ]
        return [tuple((key, row[key]) for key in columns) for row in data]

    def _write_checked_data(self, header, data: List[dict]):
        with open(
            f"{self.config.processed_folder}/{self.lab}/"
            f"{self.config.labs[self.lab]['name']}.csv",
            "w",
            encoding="utf-8",
        ) as f:
            writer = csv.DictWriter(f, fieldnames=header, delimiter=",")
            writer.writeheader()
            writer.writerows(data)

    def _write_cleaned_data(self, header, file_date, data: List[dict]):
        with open(
            f"{self.config.cleaned_folder}/{self.lab}/"
            f"{self.config.labs[self.lab]['name']}_{file_date}.tsv",
            "w",
            encoding="utf-8",
        ) as f:
            writer = csv.DictWriter(f, fieldnames=header, delimiter="\t")
            writer.writeheader()
            writer.writerows(data)

    def _warn(self, message: str):
        warning = ReleaseWarning(message)
        self.printer.print_warning(warning, indent=3)
        self.warnings.append(warning)
