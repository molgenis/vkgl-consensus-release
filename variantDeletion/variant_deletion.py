import csv
import re
from pathlib import Path
from typing import List

import pandas as pd

from preprocessing.file_comparison import FileComparing
from publication.delete_data import DataRemover
from utils.configuration import Configuration
from utils.printer import Printer
from utils.report import ReleaseError, ReleaseReport, ReleaseWarning

from .consensus_maintenance import ConsensusMaintainer


class VariantRemover:
    """
    Prepare the removal of variants that are not included anymore in the latest release
    Updates are needed on:
    - The Consensus => redefine the consensusClassification and matches or delete whole
      variant in case of Classified by one lab
    - The normalised lab data (delete the variant)
    - The processing feedback (remove feedback of the deleted variant)
    - The raw lab data (remove the deleted variant)
    - In case of duplicate normalised variants (different raw variants that are
      normalised the same):
      - Adds the raw data of the other ones to the pipeline for re-analyses
      - Removes the normalised lab data
    - Puts a remark in the history table => is included in the history part
    """

    def __init__(
        self,
        config: Configuration,
        lab: str,
        report: ReleaseReport,
        warnings: List[ReleaseWarning],
    ):
        self.config = config
        if self.config.session.signin_status != "signed in":
            self.config.session.signin(self.config.user, self.config.pwd)
        self.session = self.config.session
        self.lab = lab
        self.lab_name = config.labs[lab]["name"]
        self.lab_system = config.labs[lab]["labSystem"]
        self.printer = Printer()
        self.report = report
        self.warnings = warnings
        # Get all normalised data from the lab
        self.normalised_lab_data = self.session.get(
            table=self.lab_name, schema="VKGL", as_df=True
        )

        self.new_variants = pd.read_csv(
            f"{config.processed_folder}/{lab}/new_variants.tsv", sep="\t"
        )

        self.variants_added = False

        self.c_updater = ConsensusMaintainer(self.config, self.lab, self.warnings)

    def remove_variants(self):
        self.printer.print("🧹 Remove deleted variants", indent=1)
        n_new_variants = len(self.new_variants)
        file = Path(f"{self.config.processed_folder}/{self.lab}/deleted_variants.tsv")
        try:
            with open(file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter="\t")
                variants = list(reader)

                if len(variants) > 250:
                    raise ReleaseError("More than 250 deleted variants found")
                for variant in variants:
                    self.printer.print(
                        "Update the consensus (if relevant) and "
                        "remove normalised (if available) "
                        f"and raw lab data of variant {variant["id"]} ",
                        indent=2,
                    )
                    # Get Normalised data of the deleted variant
                    norm_variant = self._get_normalised_variant_data(variant["id"])

                    if norm_variant:
                        # Update the consensus (if deleted variant included)
                        self.c_updater.update_consensus(norm_variant["id"])

                        self.printer.print(
                            f"🗑️ Delete normalised variant: " f"{norm_variant["id"]}",
                            indent=3,
                        )
                        self.session.delete_records(
                            table=self.lab_name,
                            schema="VKGL",
                            data=[{"id": norm_variant["id"]}],
                        )

                    self.printer.print(
                        "🗑️ Remove the raw lab data, "
                        "including any ProcessingFeedback",
                        indent=3,
                    )
                    DataRemover(self.config).lab_data(self.lab, variant["id"])

                    if norm_variant and "DUP" in norm_variant["id"]:
                        self.printer.print(
                            "❗️Normalised deleted variant was a "
                            "duplicate, re-analyse remaining duplicates",
                            indent=3,
                        )
                        rerun_dupl = self._rerun_duplicates(norm_variant["id"])
                        msg = (
                            "🗑️ Delete remaining duplicate normalised variant(s):"
                            "\n                - "
                        ) + "\n- ".join([d["id"] for d in rerun_dupl])
                        self.printer.print(msg, indent=4)
                        self.session.delete_records(
                            table=self.lab_name, schema="VKGL", data=rerun_dupl
                        )

            if self.variants_added:
                self.new_variants = self.new_variants.drop_duplicates()
                self.printer.print(
                    f"📌 {len(self.new_variants) - n_new_variants} "
                    "duplicate variant(s) added for re-analyse",
                    indent=2,
                )

                variants_file = Path(
                    f"{self.config.processed_folder}/{self.lab}/" f"new_variants.tsv"
                )
                variants_file.rename(
                    f"{self.config.processed_folder}/{self.lab}/" "new_variants_ori.tsv"
                )
                self.new_variants.to_csv(
                    f"{self.config.processed_folder}/{self.lab}" f"/new_variants.tsv",
                    sep="\t",
                    index=False,
                )

        except FileNotFoundError:
            self._warn(f"{file} not found")

    def _get_normalised_variant_data(self, raw_lab_id: str):
        df_normalised = self.normalised_lab_data[
            self.normalised_lab_data["rawLabData"].isin([raw_lab_id])
        ]

        if df_normalised.empty:
            self._warn(
                f"No normalised data found for deleted " f"variant: {raw_lab_id}"
            )
            return {}

        if len(df_normalised) > 1:
            raise ReleaseError(
                "More than one normalised variant found "
                f"for this deleted variant: {raw_lab_id}"
            )

        return df_normalised.to_dict(orient="records")[0]

    def _rerun_duplicates(self, deleted_id: str):
        _id = re.sub(r"DUP\d+", "", deleted_id)
        df_dupl = self.normalised_lab_data[
            self.normalised_lab_data["id"].str.contains(_id)
        ]

        df_remaining_dupl = df_dupl[df_dupl["id"].ne(deleted_id)]
        # Check if any of the remaining duplicates is included in the consensus
        for _id in df_remaining_dupl["id"]:
            self.c_updater.update_consensus(_id, indent=4)

        raw_lab_ids = df_remaining_dupl["rawLabData"].tolist()
        folder = f"{self.config.cleaned_folder}/{self.lab}"
        file_comparing = FileComparing(
            lab=self.lab,
            lab_name=self.lab_name,
            input_folder=folder,
            report=self.report,
            warnings=self.warnings,
        )
        files = file_comparing.list_and_sort_files(desc=False)
        if not files:
            raise ReleaseError("No files with raw data found?!")
        df_cleaned_data = pd.read_csv(files[-1], sep="\t")
        df_raw_dupl = df_cleaned_data[df_cleaned_data["id"].isin(raw_lab_ids)]
        self.new_variants = pd.concat([self.new_variants, df_raw_dupl])
        self.variants_added = True

        return df_remaining_dupl[["id"]].to_dict(orient="records")

    def _warn(self, message: str):
        warning = ReleaseWarning(message)
        self.printer.print_warning(warning, indent=2)
        self.warnings.append(warning)
