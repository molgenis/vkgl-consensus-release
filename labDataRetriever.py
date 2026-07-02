from typing import List

from preprocessing.data_retrieval import DataRetriever
from utils.configuration import Configuration
from utils.printer import Printer
from utils.report import ReleaseError, ReleaseReport


class RawDataRetriever:
    """
    Main class for getting the raw lab data files from nibbler-transfer:
    - Gets the data via rsync
    - Extracts and converts if necessary to tsv or txt formats
    """

    def __init__(self, config: Configuration):
        self.config = config
        self.printer = Printer()
        self.print = self.printer.print
        self.processing_feedback: List[dict] = list()
        self.report = ReleaseReport([config.labs[lab]["name"] for lab in config.labs])

    def get_data(self):
        self.printer.print_header("🛒 Get all raw lab data")
        for lab in self.config.labs:
            lab_name = self.config.labs[lab]["name"]
            try:
                self.print(f"📥 Retrieve {lab_name} raw data")
                DataRetriever(self.config, lab).get_raw_data()
                with open(
                    f"{self.config.raw_data_folder}/{lab}/dataRetrieval.ok", "w"
                ) as f:
                    f.write(f"Raw {lab_name} successfully retrieved")
            except ReleaseError as error:
                self.printer.print_error(error)
                self.report.add_error(lab_name, ReleaseError(error))

        self.printer.print_retrieval_summary(self.report)
        if self.report.has_errors():
            raise ValueError("Getting the raw data of one or more labs failed")


if __name__ == "__main__":
    try:
        RawDataRetriever(Configuration()).get_data()
    except ValueError as e:
        print(f"\n‼️ {e} ‼️")
