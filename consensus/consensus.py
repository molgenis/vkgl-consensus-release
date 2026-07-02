from collections import Counter
from pathlib import Path
from typing import List

import pandas as pd

from utils.configuration import Configuration
from utils.printer import Printer
from utils.report import ReleaseError, ReleaseWarning
from utils.validation import check_multiple_classifications


class Consensus:
    """
    Derive consensus for newly normalised variants:
    - Combine data from the different labs:
        - Either from files
        - Or from the consensus
    """

    def __init__(self, config: Configuration):
        self.config = config
        if self.config.session.signin_status != "signed in":
            self.config.session.signin(self.config.user, self.config.pwd)
        self.printer = Printer()
        self.session = self.config.session
        self.classifications = self.session.get(
            "VariantClassifications", schema="ReferenceLists", as_df=True
        )
        self.one_lab = "Classified by one lab"
        self.no_consensus = "No consensus"
        self.opposite_consensus = "Opposite classifications"
        self.warnings: List[ReleaseWarning] = list()
        Path(config.consensus_folder).mkdir(parents=True, exist_ok=True)

    def create_consensus(self) -> List[ReleaseWarning]:
        self.printer.print("🧩 Combine normalised lab data", indent=1)
        df_consensus = pd.DataFrame()
        labs_no_data = []
        for lab in self.config.labs:
            try:
                df_lab = pd.read_csv(
                    f"{self.config.normalised_folder}/{lab}/"
                    f"{self.config.labs[lab]['name']}.csv",
                    dtype=str,
                )
                self.printer.print(
                    "🆕 New and/or updated variants found for "
                    f"{self.config.labs[lab]['name']}",
                    indent=2,
                )
                # Remove duplicate IDs
                df_dup = df_lab[df_lab["id"].str.contains("DUP")].copy()
                df_dup["id"] = df_dup["id"].str.replace(r"DUP\d*$", "", regex=True)
                ids_different_classifications = check_multiple_classifications(df_dup)
                if ids_different_classifications:
                    self._warn(
                        f"Remove duplicate variants with different "
                        f"classifications: "
                        f"{" and ".join(ids_different_classifications)} for "
                        f"{self.config.labs[lab]['name']}",
                        indent=3,
                    )
                    for _id in ids_different_classifications:
                        df_lab = df_lab[~df_lab["id"].str.match(rf"^{_id}(DUP\d+)?$")]
                n_initial = len(df_lab)
                # Otherwise only keep the first duplicate value
                df_lab = df_lab[
                    df_lab["id"].str.contains(r"DUP1$", regex=True, na=False)
                    | ~df_lab["id"].str.contains(r"DUP\d+$", regex=True, na=False)
                ]

                if len(df_lab) != n_initial:
                    self.printer.print(
                        f"⚠️ {n_initial - len(df_lab)} duplicate variants "
                        f"found for {self.config.labs[lab]['name']}, "
                        f"only kept the first occurrence",
                        indent=3,
                    )
                df_lab[f"{lab}Data"] = df_lab["id"]
                df_lab["id"] = df_lab["id"].str.replace(f"{lab.upper()}_", "")
                df_lab["id"] = df_lab["id"].str.replace("DUP1", "")
                # Replace classification short name by classification (b -> Benign)
                # to use in Consensus table, could be replaced by a computed expression
                df_lab["classification"] = df_lab["classification"].replace(
                    dict(self.classifications[["id", "classification"]].values)
                )

                # Drop irrelevant columns
                df_lab.drop(
                    columns=[
                        "rawLabData",
                        "vv_url",
                        "exon",
                        "variantType",
                        "location",
                        "effect",
                        "labUploadDate",
                    ],
                    inplace=True,
                )

                if not df_consensus.empty:
                    df_consensus = df_consensus.merge(
                        df_lab,
                        how="outer",
                        suffixes=(None, f"_{lab}"),
                        on=[
                            "id",
                            "chromosome",
                            "start",
                            "stop",
                            "ref",
                            "alt",
                            "gene",
                            # "cDNA",
                            # "transcript",
                            # "protein",
                            "hgvs",
                            "hgvsGRCh38",
                            "posGRCh38",
                            "refGRCh38",
                            "altGRCh38",
                        ],
                    )

                else:
                    df_consensus = df_lab
                df_consensus.rename(columns={"classification": lab}, inplace=True)
            except FileNotFoundError:
                self._warn(
                    f"No new or updated normalised variants found for "
                    f"{self.config.labs[lab]['name']}"
                )
                labs_no_data.append(lab)

        if df_consensus.empty:
            raise ReleaseError("No new or updated consensus data available")

        # Check if transcript, cDNA and protein is the same for all labs
        self.printer.print("🔍 Check transcript, cDNA and protein values", indent=1)
        for column in ["transcript", "cDNA", "protein"]:
            df_consensus[column] = df_consensus.apply(
                lambda x: self._check_column_values(column, x), axis=1
            )

        for lab in labs_no_data:
            df_consensus[lab] = None
            df_consensus[f"{lab}Data"] = None

        self.printer.print(
            "➡️ Add classification of labs not in the update, "
            "but that are in the previous Consensus",
            indent=1,
        )
        _ids = list(set(df_consensus["id"].tolist()))
        if len(_ids) <= 300:  # Filter seems to work fine up till 300 IDs
            df_previous = self.session.get(
                "Consensus", schema="VKGL", query_filter=f"id=={_ids}", as_df=True
            )
        else:
            df_previous_all = self.session.get("Consensus", schema="VKGL", as_df=True)
            df_previous = df_previous_all[df_previous_all["id"].isin(_ids)]

        self.printer.print(
            f"{len(df_previous)} of the new/updated variants are in the "
            f"{self.config.previous} consensus",
            indent=2,
        )
        if not df_previous.empty:
            df_consensus = df_consensus.merge(
                df_previous, how="outer", on="id", suffixes=(None, "_previous")
            )
            # Fill (if available) missing lab classifications from the previous release
            for lab in self.config.labs:
                df_consensus[lab] = df_consensus[lab].fillna(
                    df_consensus[f"{lab}_previous"]
                )
                df_consensus[f"{lab}Data"] = df_consensus[f"{lab}Data"].fillna(
                    df_consensus[f"{lab}Data_previous"]
                )

        self.printer.print("🤝 Derive consensus classification", indent=1)
        columns = ["id"]
        columns.extend(self.config.labs)
        df_classification = self.consensus_classification(df_consensus[columns].copy())
        df_consensus = df_consensus.merge(
            df_classification, how="outer", on="id", suffixes=("_previous", None)
        )

        # Drop redundant columns
        if "mg_draft" in df_consensus.columns:
            columns2remove = ["mg_draft"]
        else:
            columns2remove = []
        for column in df_consensus.columns:
            if "_previous" in column:
                columns2remove.append(column)

        df_consensus.drop(columns=columns2remove, inplace=True)

        self.check4duplicates(df_consensus)

        # Save new/updated Consensus variants to file
        df_consensus["matches"] = df_consensus["matches"].apply(
            lambda x: "" if pd.isna(x) else int(x)
        )
        df_consensus.to_csv(
            f"{self.config.consensus_folder}/Consensus.csv", index=False
        )

        return self.warnings

    def check4duplicates(self, df: pd.DataFrame):
        with self.printer.indentation():
            self.printer.print("🔍 Check for duplicate IDs in the combined lab data")
            duplicates = df[df.duplicated(["id"], keep=False)]
            if not duplicates.empty:
                raise ReleaseError(
                    f"Duplicate IDs found in the consensus"
                    f"\n{'\n'.join(f"\t\t- {_id}" for _id in duplicates['id'].values)}"
                )

    def consensus_classification(self, df: pd.DataFrame):
        # Replace classification with the (combined) consensus classifications
        for lab in self.config.labs:
            df[lab] = df[lab].replace(
                dict(self.classifications[["classification", "consensus"]].values)
            )

            # fill NA with empty value otherwise an error occurs when doing x==x check
            df[lab] = df[lab].fillna("")
        # Combine lab classifications into one list
        df["all"] = [
            [x for x in row if x != ""]
            for row in df[self.config.labs.keys()].values.tolist()
        ]
        df[["consensusClassification", "matches"]] = df["all"].apply(
            lambda x: pd.Series(self.check_classification(x))
        )
        df.drop(columns=self.config.labs, inplace=True)
        df.drop(columns="all", inplace=True)

        return df

    def check_classification(self, classifications):
        if len(classifications) == 1:
            return self.one_lab, int(1)
        counter = dict(Counter(classifications))
        if len(counter) == 1:
            return list(counter.keys())[0], int(list(counter.values())[0])
        # Conflicting should be checked first since it is a form of 'no consensus'
        # and wins over it
        if "(Likely) benign" in counter and "(Likely) pathogenic" in counter:
            return self.opposite_consensus, None
        # No consensus if variant has VUS and any other classification
        if "VUS" in counter:
            return self.no_consensus, None

        raise ReleaseError(
            f"Something went wrong while determining the consensus "
            f"{classifications}"
        )

    def _check_column_values(self, check: str, row: pd.Series):
        lab_columns = [c for c in list(row.index) if check in c]
        values = row[lab_columns].values.tolist()

        values = [x for x in values if x == x]
        if not values:
            return None
        values.sort()
        if len(set(values)) > 1:
            self._warn(
                f"{check} values {' and '.join(values)} found for variant "
                f"{row["id"]}, the last one will be chosen",
                indent=2,
            )

        return values[-1]

    def _warn(self, message: str, indent: int = 2):
        warning = ReleaseWarning(message)
        self.printer.print_warning(warning, indent=indent)
        self.warnings.append(warning)
