from typing import List

import pandas as pd

from utils.configuration import Configuration
from utils.printer import Printer
from utils.report import ReleaseWarning


class PublicInformation:
    """
    1.) Create public consensus based on the complete consensus, excluding Opposites and
        No consensus classifications.
        Modifications done:
        - not all columns are included
        - define variant (chr:start gene ref > alt)
        - Add supporting labs based on matches
    2.) Create files to put on the download server:
        - One with GenomeReferenceBuild 37 information
        - One with GenomeReferenceBuild 38 information
    3.) Generate Consensus classification counts:
        - Per Consensus classification
        - Per Classification within Classified by one lab classification
    """

    def __init__(self, config: Configuration):
        self.config = config
        if self.config.session.signin_status != "signed in":
            self.config.session.signin(self.config.user, self.config.pwd)
        self.printer = Printer()
        self.session = self.config.session
        self.warnings: List[ReleaseWarning] = list()
        self.classifications = self.session.get(
            "VariantClassifications", schema="ReferenceLists", as_df=True
        )

    def generate_public_information(self) -> List[ReleaseWarning]:
        self.printer.print("📥 Get consensus data", indent=1)
        df_consensus = self.session.get(table="Consensus", schema="VKGL", as_df=True)
        exclude = ["No consensus", "Opposite classifications", "Classified by one lab"]
        df_public = df_consensus[~df_consensus["consensusClassification"].isin(exclude)]
        if df_public.empty:
            self._warn("No (Likely) benign, pathogenic or VUS classifications?!")
        df_public["supportingLabs"] = df_public["matches"].astype(str) + " labs"

        self.printer.print("🔄 Update Classified by one lab data", indent=1)
        df_one_lab = df_consensus[
            df_consensus["consensusClassification"] == "Classified by one lab"
        ]
        if df_one_lab.empty:
            self._warn("No Classified by one lab classifications?!")
        df_one_lab["supportingLabs"] = df_one_lab["matches"].astype(str) + " lab"
        labs = list(self.config.labs.keys())
        consensus = "consensusClassification"
        # Get classification of the specific lab (first non-NaN occurrence)
        df_one_lab[consensus] = df_one_lab[labs].bfill(axis=1).iloc[:, 0]
        # Get counts of the real classifications
        df_one_lab_counts = (
            df_one_lab.groupby(consensus).size().reset_index(name="count")
        )
        df_one_lab[consensus] = df_one_lab[consensus].replace(
            dict(self.classifications[["classification", "consensus"]].values)
        )

        df_public = pd.concat([df_public, df_one_lab], ignore_index=True)

        df_public["variant"] = (
            df_public["chromosome"]
            + ":"
            + df_public["start"].astype(str)
            + " "
            + df_public["gene"]
            + " "
            + df_public["ref"]
            + ">"
            + df_public["alt"]
        )

        self.printer.print("✨ Create the Public Consensus", indent=1)
        # Remove irrelevant columns
        schema_meta = self.session.get_schema_metadata(name="Public")
        table_meta = []
        for table in schema_meta.tables:
            if table.name == "PublicConsensus":
                table_meta = table
        columns = [c.id for c in table_meta.columns if c.id[0:3] != "mg_"]
        df_public_file = df_public[columns]
        df_public_file.to_csv(
            f"{self.config.consensus_folder}/PublicConsensus.csv", index=False
        )

        self.printer.print("✨ Create file for Beacon v2 integration", indent=1)
        df_beacon = df_public_file.copy()
        mapping = {
            # Not in Public Consensus"": "variant type",
            "consensusClassification": "variant effect type",
            "hgvs": "genomic HGVS id",
            "transcript": "transcript HGVS ids",
            "protein": "protein HGVS ids",
            # Set default to GRCH37 "": "genomic assembly id",
            # = chromosome: "refseq assembly id",
            "gene": "gene id",
            "chromosome": "chromosome",
            # Not available "": "chromosomal region",
            "start": "start position",
            "stop": "stop position",
            "ref": "reference allele",
            "alt": "alternate allele",
            "cDNA": "cDNA",
        }

        df_beacon.rename(columns=mapping, inplace=True)
        df_beacon["genomic assembly id"] = "GRCh37"
        df_beacon["refseq assembly id"] = df_beacon["chromosome"]
        df_beacon.to_csv(
            f"{self.config.consensus_folder}/Genomic variants.csv", index=False
        )

        self.printer.print("✨ Create files for download", indent=1)

        df_public_file[[c for c in columns if "GRCh38" not in c]].to_csv(
            f"{self.config.consensus_folder}/VKGL_public_consensus_"
            f"{self.config.release}_GRCh37.tsv",
            index=False,
            sep="\t",
        )

        columns38 = [
            "chromosome",
            "posGRCh38",
            "refGRCh38",
            "altGRCh38",
            "gene",
            "hgvsGRCh38",
            "consensusClassification",
            "supportingLabs",
            "id",
        ]

        df_public38 = df_public[columns38]
        df_public38.rename(
            columns={
                "posGRCh38": "start",
                "refGRCh38": "ref",
                "altGRCh38": "alt",
                "hgvsGRCh38": "hgvs",
            },
            inplace=True,
        )

        df_public38.insert(0, "variant", "")
        df_public38["variant"] = (
            df_public38["chromosome"]
            + ":"
            + df_public38["start"].astype(str)
            + " "
            + df_public38["gene"]
            + " "
            + df_public38["ref"]
            + ">"
            + df_public["alt"]
        )

        df_public38.to_csv(
            f"{self.config.consensus_folder}/VKGL_public_consensus_"
            f"{self.config.release}_GRCh38.tsv",
            index=False,
            sep="\t",
        )

        self.printer.print("🧮 Calculate the Classification counts", indent=1)
        # Count classification categories:
        df_counts = (
            df_consensus.groupby("consensusClassification")
            .size()
            .reset_index(name="count")
        )

        # Transpose one lab counts
        df_counts_one_lab = df_one_lab_counts.set_index("consensusClassification").T
        # Set the right column name
        df_counts_one_lab.insert(0, "consensusClassification", "Classified by one lab")

        df_counts = df_counts.merge(
            df_counts_one_lab, how="outer", on=["consensusClassification"]
        )
        count_columns = list(df_counts.columns)
        count_columns.remove("consensusClassification")
        df_counts[count_columns] = df_counts[count_columns].astype("Int64")

        df_counts.to_csv(
            f"{self.config.consensus_folder}/ConsensusCounts.csv", index=False
        )

        return self.warnings

    def _warn(self, message: str, indent: int = 2):
        warning = ReleaseWarning(message)
        self.printer.print_warning(warning, indent=indent)
        self.warnings.append(warning)
