import asyncio
import logging
import sys
from datetime import datetime

from consensus.consensus import Consensus
from utils.configuration import Configuration
from utils.printer import Printer
from utils.report import ReleaseError, ReleaseWarning


class PrepareScratchRun:
    """
    For several reasons it might be necessary to do a fresh run for a specific lab
    (all out-all in), for example new file lay-out or a new lab system.
    This is the main class for preparing this and the Main task if to remove all data
    of the specific lab from:
    - The consensus (redefine Consensus Classification or delete complete variant in
    case of Classified by one lab)
    - Truncate normalised data table
    - Remove all lab related ProcessingFeedback
    - Truncate rawLabData
    """

    def __init__(self, config: Configuration, lab2clean: str):
        self.config = config
        if self.config.session.signin_status != "signed in":
            self.config.session.signin(self.config.user, self.config.pwd)
        self.consensus = Consensus(self.config)
        self.session = self.config.session
        self.lab = lab2clean
        self.printer = Printer()
        self.print = self.printer.print

    async def prepare_scratch_run(self):
        # Set up the logger
        logging.basicConfig(
            level="INFO", format=" %(levelname)s: %(name)s: %(message)s"
        )
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)

        if lab not in self.config.labs:
            raise ReleaseError(f"Specified lab: {lab} not found in the list")

        lab_name = self.config.labs[lab]["name"]
        self.printer.print_header(
            f"⚙️ Prepare scratch run for {lab_name} "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        self.printer.print(
            f"🔄 Update the Consensus, remove all links to {lab_name} "
            f"and redefine classification and matches",
            indent=1,
        )
        self._update_consensus(lab_name)

        self.printer.print("⬇️ Truncate normalised data table", indent=1)
        self.session.truncate(table=lab_name, schema="VKGL")

        self.printer.print(f"🧹 Remove {lab_name} ProcessingFeedback", indent=1)
        self._update_processing_feedback(lab_name)

        self.printer.print("⬇️ Truncate raw lab data table", indent=1)
        self.session.truncate(table=lab_name, schema="RawLabData")

    def _update_consensus(self, lab_name):
        # Get all consensus variants where the lab is included
        df_consensus = self.session.get(table="Consensus", schema="VKGL", as_df=True)
        df_lab = df_consensus[df_consensus[f"{self.lab}Data"].notna()]
        if df_lab.empty:
            self._warn(f"{lab_name} has no variants in the consensus")
            return

        df_classified1lab = df_lab[
            df_lab["consensusClassification"] == "Classified by one lab"
        ]
        if not df_classified1lab.empty:
            self.printer.print(
                f"🗑️ Delete {len(df_classified1lab)} Classified by one "
                "lab variants from the Consensus",
                indent=2,
            )
            to_delete = df_classified1lab[["id"]].to_dict(orient="records")
            self.session.delete_records(
                table="Consensus", schema="VKGL", data=to_delete
            )
        else:
            self.printer.print(
                "🗑️ No Classified by one lab variants need"
                "to be removed from the Consensus",
                indent=2,
            )

        df_others = df_lab[df_lab["consensusClassification"] != "Classified by one lab"]

        df_others[self.lab] = ""
        df_others[f"{self.lab}Data"] = ""

        df_others_updated = self.consensus.consensus_classification(df_others.copy())
        df_others.set_index("id", inplace=True)
        df_others.update(
            df_others_updated.set_index("id")[["consensusClassification", "matches"]],
            overwrite=True,
        )
        df_others.reset_index(inplace=True)

        self.printer.print(f"🔄 Update {len(df_others)} Consensus variants ", indent=2)
        df_others["matches"] = df_others["matches"].astype("Int64")
        self.session.save_table(table="Consensus", schema="VKGL", data=df_others)

    def _update_processing_feedback(self, lab_name):
        _filter = f"lab.id == {self.lab}"
        df_pf = self.session.get(
            table="ProcessingFeedback",
            schema="RawLabData",
            query_filter=_filter,
            as_df=True,
        )

        if df_pf.empty:
            self._warn(f"{lab_name} has no processing feedback")
            return
        self.printer.print(
            f"🗑️ Delete {len(df_pf)} processing feedback records", indent=2
        )
        to_delete = df_pf[["id"]].to_dict(orient="records")

        self.session.delete_records(
            table="ProcessingFeedback", schema="RawLabData", data=to_delete
        )

    def _warn(self, message: str, indent: int = 2):
        warning = ReleaseWarning(message)
        self.printer.print_warning(warning, indent=indent)


if __name__ == "__main__":
    lab = sys.argv[1]
    try:
        asyncio.run(PrepareScratchRun(Configuration(), lab).prepare_scratch_run())
    except ValueError as e:
        print(f"\n‼️ {e} ‼️")
