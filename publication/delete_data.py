import pandas as pd

from utils.configuration import Configuration
from utils.printer import Printer
from utils.report import ReleaseError


class DataRemover:
    """
    This class is responsible for deleting data
    """

    def __init__(
        self,
        config: Configuration,
    ):
        self.config = config
        self.printer = Printer()
        self.print = self.printer.print
        self.session = self.config.session

    def processing_feedback(
        self, lab: str, step: str = None, variant: str = None, indent: int = 0
    ):
        """
        Remove based on the processing step and IDs in the file data from the
        ProcessingFeedback table
        """
        lab_name = self.config.labs[lab]["name"]
        self.printer.print(f"🗑 Delete {lab_name} processing feedback", indent=indent)

        with self.printer.indentation():
            _ids = [variant]
            if step == "preprocessing":
                df = pd.read_csv(
                    f"{self.config.processed_folder}/{lab}/{lab_name}.csv", dtype=str
                )
                _ids = list(set(df["id"].tolist()))
            if step == "normalisation":
                df = pd.read_csv(
                    f"{self.config.processed_folder}/{lab}/new_variants.tsv",
                    sep="\t",
                )
                _ids = list(set(df["id"].tolist()))
            try:
                # Get the right primary keys
                _filter = f"lab.id == {lab} and processingStep.id == {step}"
                if variant:
                    _filter = f"{lab}.id == {variant}"
                df_feedback = self.session.get(
                    table="ProcessingFeedback",
                    schema="RawLabData",
                    columns=["id", lab],
                    query_filter=_filter,
                    as_df=True,
                )

                df2delete = df_feedback[df_feedback[lab].isin(_ids)]
                delete_list = df2delete.to_dict("records")

                self.printer.print(
                    f"🧹 Remove {len(delete_list)} row(s) from the "
                    f"ProcessingFeedback table",
                    indent=indent,
                )
                self.session.delete_records(
                    "ProcessingFeedback", "RawLabData", data=delete_list
                )
            except KeyError as e:
                raise ReleaseError("Error deleting data from ProcessingFeedback") from e

    def lab_data(self, lab: str, variant: str):
        """
        Remove based on an ID data from the raw lab data table
        """
        lab_name = self.config.labs[lab]["name"]
        self.printer.print(f"📝 Delete {lab_name} raw variant: {variant}", indent=4)

        # First check if any ProcessingFeedback exists, if so delete
        self.processing_feedback(lab=lab, variant=variant, indent=4)
        self.session.delete_records(
            table=lab_name, schema="RawLabData", data=[{"id": variant}]
        )
