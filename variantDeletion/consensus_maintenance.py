from typing import List

from consensus.consensus import Consensus
from utils.configuration import Configuration
from utils.printer import Printer
from utils.report import ReleaseError, ReleaseWarning


class ConsensusMaintainer:
    """
    If a variant has been deleted the consensus should be updated:
    - Redefine the consensusClassification and matches columns and remove
      the link to the variant
    - Or delete the whole variant in case of a classification by one lab
    """

    def __init__(
        self,
        config: Configuration,
        lab: str,
        warnings: List[ReleaseWarning],
    ):
        self.config = config
        self.session = config.session
        self.lab = lab
        self.printer = Printer()
        self.warnings = warnings
        self.consensus = Consensus(self.config)

    def update_consensus(self, variant, indent: int = 3):
        try:
            # Get the consensus data for this deleted variant
            query = f"{self.lab}Data.id=={variant}"
            df_consensus = self.session.get(
                table="Consensus", schema="VKGL", query_filter=query, as_df=True
            )
            if df_consensus.empty:
                self._warn(
                    f"No consensus data found for normalised variant: {variant}",
                    indent=indent,
                )
                return "Not in the consensus", {}

            if len(df_consensus) > 1:
                raise ReleaseError(
                    "More than one variant found in the "
                    f"consensus for this deleted variant: {variant}"
                )

            if df_consensus["consensusClassification"].iloc[0] == (
                "Classified by one " "lab"
            ):
                self.printer.print(
                    f"🗑️ Delete complete variant ("
                    f"{df_consensus["id"].iloc[0]}) from the Consensus",
                    indent=indent,
                )
                self.session.delete_records(
                    table="Consensus",
                    schema="VKGL",
                    data=[{"id": df_consensus["id"].iloc[0]}],
                )
            else:
                df_consensus.loc[0, self.lab] = ""
                df_consensus.loc[0, f"{self.lab}Data"] = ""

                df_updated_consensus = self.consensus.consensus_classification(
                    df_consensus.copy()
                )
                df_consensus.set_index("id", inplace=True)
                df_consensus.update(
                    df_updated_consensus.set_index("id")[
                        ["consensusClassification", "matches"]
                    ],
                    overwrite=True,
                )
                df_consensus.reset_index(inplace=True)

                self.printer.print(
                    "🔄 Update the Consensus of variant "
                    f"{df_consensus["id"].iloc[0]}",
                    indent=indent,
                )
                self.session.save_table(
                    table="Consensus", schema="VKGL", data=df_consensus
                )

        except Exception as e:
            raise ReleaseError(
                "Something went wrong while updating the consensus for "
                f"{variant}: {e}"
            )

    def _warn(self, message: str, indent: int = 2):
        warning = ReleaseWarning(message)
        self.printer.print_warning(warning, indent=indent)
        self.warnings.append(warning)
