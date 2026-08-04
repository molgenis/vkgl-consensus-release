import shutil
from datetime import datetime
from pathlib import Path
from typing import List

import pandas as pd

from .configuration import Configuration
from .printer import Printer
from .report import ReleaseError, ReleaseReport, ReleaseWarning
from .utils import get_row_count


class Validator:
    """
    This class is responsible for validating the data in a release step. Validation
    consists of:
    1. Checking file counts
    2. Check for duplicated rows and deduplicate the file
    """

    def __init__(
        self,
        lab: str,
        config: Configuration,
        processing_feedback: List[dict],
        report: ReleaseReport,
        warnings: List[ReleaseWarning],
    ):
        self.config = config
        self.file_info = {}
        self.files = []
        self.lab = lab
        self.lab_name = self.config.labs[lab]["name"]
        self.printer = Printer()
        self.processing_feedback = processing_feedback
        self.report = report
        self.session = self.config.session
        self.validation_failed = False
        self.warnings = warnings

    def validate_normalisation(self):
        self.printer.print(f"🕵 Validate {self.lab_name} normalisation step")
        self._validate_normalised_file_counts()
        self.files = [self.config.normalised_folder / self.lab / f"{self.lab_name}.csv"]
        self._check_duplicate_ids_existing_data()
        self._check_duplicate_ids(step="normalisation", remove_all=False)
        if not self.validation_failed:
            self.printer.print("✅ Normalisation successfully validated", indent=1)

    def validate_preprocessing(self):
        self.printer.print(f"🕵 Validate {self.lab_name} preprocessing step")
        for folder in [
            self.config.raw_data_folder,
            self.config.processed_folder,
            self.config.cleaned_folder,
        ]:
            self._get_file_info(f"{folder}/{self.lab}")
        self._check_file_counts()
        self._check_duplicate_ids("preprocessing")
        if not self.validation_failed:
            self.printer.print("✅ All files successfully validated", indent=1)

    def _get_file_info(self, data_folder):
        for file in Path(data_folder).iterdir():
            if file.is_file() and file.suffix != ".gz":
                self.file_info.setdefault(file.stem, {})[file.suffix.lower()] = (
                    get_row_count(file)
                )
                self.files.append(file)

    def _check_file_counts(self):
        for file in self.file_info:
            file_counts = []
            for suffix in self.file_info[file].keys():
                file_counts.append(self.file_info[file][suffix]["n_rows"])
            if len([set(file_counts)]) != 1:
                self.validation_failed = True
                raise ReleaseError(
                    f"Counts don't match for different formats of {file.name}"
                )
        if not self.validation_failed:
            self.printer.print(
                "✅ The counts of the same files with different delimiters are OK",
                indent=2,
            )

    def _validate_normalised_file_counts(self):
        try:
            to_be_normalised = (
                f"{self.config.processed_folder}/" f"{self.lab}/new_variants.tsv"
            )
            normalised = (
                f"{self.config.normalised_folder}/" f"{self.lab}/{self.lab_name}.csv"
            )
            df_to_be = pd.read_csv(to_be_normalised, sep="\t", dtype=str)
            df_normalised = pd.read_csv(normalised, dtype=str)
            if len(df_to_be) != len(df_normalised):
                self.validation_failed = True
                missing = df_to_be[~df_to_be["id"].isin(df_normalised["rawLabData"])]
                message = f"{len(missing)} variant(s) couldn't be normalised"
                self._warn(
                    f"{message}:"
                    f"\n{'\n'.join(f"\t\t- {_id}" for _id in missing['id'].values)}"
                )
            else:
                message = "All new / updated variants could be normalised"
                self.printer.print(f"✅ {message}", indent=1)
            self.report.update_summary(self.lab_name, {"normalised": message})

        except FileNotFoundError as e:
            raise ReleaseError(f"{str(e).replace('[Errno 2] ', '')}")

    def _check_duplicate_ids(self, step: str, remove_all: bool = False):
        for file in self.files:
            if str(self.config.raw_data_folder) in str(file.parent):
                continue
            delimiter = ","
            if file.suffix in [".tsv", ".txt"]:
                delimiter = "\t"
            df = pd.read_csv(file, sep=delimiter, dtype=str)
            if "id" not in df.columns or not df["id"].notna().any():
                continue
            duplicates = df[df.duplicated(subset="id", keep=False)]
            if not duplicates.empty:
                self.validation_failed = True
                dupl_file = file.parent / "duplicates.csv"
                duplicates.to_csv(dupl_file, index=False)
                duplicates_with_multiple_class = []
                if step == "normalisation":
                    duplicates_with_multiple_class = check_multiple_classifications(
                        duplicates
                    )

                for row in duplicates.to_dict("records"):
                    if row["id"] in duplicates_with_multiple_class:
                        feedback = {
                            self.lab: row.get("rawLabData") or row.get("id"),
                            "lab": self.lab,
                            "processingStep": step,
                            "feedback": "Duplicate ID with different classifications, "
                            "excluded from further processing",
                            "processingDate": datetime.today().strftime("%Y-%m-%d"),
                        }
                    else:
                        feedback = {
                            self.lab: row.get("rawLabData") or row.get("id"),
                            "lab": self.lab,
                            "processingStep": step,
                            "feedback": "Duplicate ID after normalisation",
                            "processingDate": datetime.today().strftime("%Y-%m-%d"),
                        }
                    self.processing_feedback.append(feedback)
                self._warn(
                    f"{len(duplicates)} duplicate IDs found in {file} of "
                    f"which {len(duplicates_with_multiple_class)} with multiple "
                    f"classifications. Data can be found in {dupl_file}:"
                    f"\n{'\n'.join(
                        f"\t\t- {_id}" for _id in set(duplicates['id'].values))}"
                )

                df["id"] = df.groupby("id")["id"].transform(self._add_dup2ids)
                if remove_all:
                    all_file = Path(f"{file.parent}/{file.stem}_all{file.suffix}")
                    shutil.move(file, all_file)
                    df_dedup = df.drop(duplicates.index)
                    df_dedup.to_csv(file, index=False)
                else:
                    df.to_csv(file, index=False)

            else:
                self.printer.print(
                    f"✅ No duplicate IDs found in {file.name}", indent=2
                )

    def _check_duplicate_ids_existing_data(self):
        self.session.signin(self.config.user, self.config.pwd)
        self.printer.print(
            "🔍 Check if an ID with a different lab ID already exists in "
            "the consensus",
            indent=1,
        )
        file = f"{self.config.normalised_folder}/{self.lab}/" f"{self.lab_name}.csv"
        df = pd.read_csv(file, dtype=str)
        df_existing = self.session.get(
            table=f"{self.lab_name}", schema="VKGL", as_df=True
        )
        df_existing["id"] = df_existing["id"].str.replace(r"DUP\d*$", "", regex=True)
        _ids = list(set(df["id"].tolist()))
        df_exists = df_existing[df_existing["id"].isin(_ids)]

        df_check = df.merge(
            df_exists, on="id", how="inner", suffixes=("_new", "_existing")
        )

        df_differences = df_check.loc[
            ~(df_check["rawLabData_new"] == df_check["rawLabData_existing"])
        ]

        if not df_differences.empty:
            _ids = df_differences["id"].tolist()
            self._warn(
                "ID with different lab ID already exists in the "
                f"consensus: {" and ".join(_ids)}"
            )
            self.printer.print(
                "‼️ Remove listed IDs by hand from the normalised "
                "data after the consensus has been updated ‼️",
                indent=2,
            )
            df_new = pd.concat([df, df_exists[df_exists["id"].isin(_ids)]], axis=0)
            df_differences["id"].to_csv(
                f"{self.config.normalised_folder}/{self.lab}/" f"to_be_deleted.csv",
                index=False,
            )
            df_new.to_csv(file, index=False)

        else:
            self.printer.print(
                "✅ No IDs with a different lab ID found in the existing data",
                indent=3,
            )

    @staticmethod
    def _add_dup2ids(_id):
        if len(_id) == 1:
            return _id
        return [f"{x}DUP{i + 1}" for i, x in enumerate(_id)]

    def _warn(self, message: str):
        warning = ReleaseWarning(message)
        self.printer.print_warning(warning, indent=2)
        self.warnings.append(warning)


def check_multiple_classifications(df: pd.DataFrame):
    classification_counts = df.groupby("id")["classification"].nunique()
    dupl_ids = classification_counts[classification_counts > 1].index.tolist()
    return dupl_ids
