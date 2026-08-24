import asyncio
import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import List

from consensus.consensus import Consensus
from consensus.public_information import PublicInformation
from normalisation.normalise import Normalisation
from preprocessing.data_preparation import DataPreparer
from preprocessing.data_retrieval import DataRetriever
from preprocessing.file_comparison import FileComparing
from publication.lab_data import LabPublisher
from publication.normalised_data import NormalisedPublisher
from publication.publish_consensus import Publisher
from utils.configuration import Configuration
from utils.printer import Printer
from utils.report import ReleaseError, ReleaseReport, ReleaseWarning
from utils.utils import batched
from utils.validation import Validator
from variantDeletion.variant_deletion import VariantRemover


class ReleasePipeline:
    """
    Main class for performing the VKGL data release
    - Preprocess the data from the labs (download, check new variants, normalise)
    - Generate the consensus
    """

    def __init__(self, config: Configuration):
        self.config = config
        self.printer = Printer()
        self.print = self.printer.print
        self.processing_feedback: List[dict] = list()
        self.report = ReleaseReport([config.labs[lab]["name"] for lab in config.labs])

    async def run_release(self):
        # Set up the logger
        logging.basicConfig(
            level="INFO", format=" %(levelname)s: %(name)s: %(message)s"
        )
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)

        for lab in self.config.labs:
            lab_name = self.config.labs[lab]["name"]
            self.report.default_summary(lab_name=lab_name)
            self.report.update_summary(lab_name, {"prev_release": self.config.previous})
            self.printer.print_header(
                f"⚙️ Preprocess {lab_name} data, "
                f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            self.processing_feedback.clear()
            self.prepare_data(lab)

            if not self.report.has_lab_errors(lab_name):
                try:
                    await LabPublisher(
                        self.config, self.processing_feedback
                    ).publish_data(lab)
                except ReleaseError as error:
                    self.printer.print_error(error)
                    self.report.add_error(
                        "publishing",
                        ReleaseError(
                            f"Publishing the preprocessed {lab_name} data failed"
                        ),
                    )
            else:
                self.report.add_error(
                    "publishing",
                    ReleaseError(f"Preprocessed {lab_name} data won't be published"),
                )

            if not self.report.has_lab_errors(lab_name):
                self.processing_feedback.clear()
                await self.normalise_lab_data(lab)

            if not self.report.has_lab_errors(lab_name):
                try:
                    await NormalisedPublisher(
                        self.config, self.processing_feedback
                    ).publish_data(lab)
                except ReleaseError as error:
                    self.printer.print_error(error)
                    self.report.add_error(
                        "publishing",
                        ReleaseError(
                            f"Publishing the normalised {lab_name} data failed"
                        ),
                    )
            else:
                self.report.add_error(
                    "publishing",
                    ReleaseError(f"Normalised {lab_name} data won't be published"),
                )

        if not self.report.has_errors():
            self.printer.print_header(
                f"✨ Create / update the consensus, "
                f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            self.create_consensus()

        else:
            self.report.add_error(
                "consensus", ReleaseError("Creating the consensus won't start")
            )
            self.report.add_error(
                "publishing", ReleaseError("Consensus data won't be published")
            )
            self.printer.print_release_summary(self.report)
            raise ValueError("Preprocessing the data of one or more labs failed")

        if not self.report.has_errors():
            self.printer.print_header("📝 Publish the Consensus")
            try:
                await Publisher(
                    self.config, self.processing_feedback
                ).publish_consensus()
            except ReleaseError as error:
                self.printer.print_error(error)
                self.report.add_error(
                    "publishing", ReleaseError("Publishing the Consensus failed")
                )
        else:
            self.report.add_error(
                "publishing", ReleaseError("Consensus won't be published")
            )
            self.printer.print_release_summary(self.report)
            raise ValueError("Creating the consensus failed")

        if not self.report.has_errors():
            self.printer.print_header(
                f"✨ Create the Public Information, "
                f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            self.public_information()

        else:
            self.report.add_error(
                "consensus", ReleaseError("Creating the public information won't start")
            )
            self.report.add_error(
                "publishing", ReleaseError("Public consensus info won't be published")
            )
            self.printer.print_release_summary(self.report)
            raise ValueError("Creating the consensus failed")

        if not self.report.has_errors():
            self.printer.print_header("📝 Publish the Public Information")
            try:
                await Publisher(
                    self.config, self.processing_feedback
                ).publish_consensus(public=True)
            except ReleaseError as error:
                self.printer.print_error(error)
                self.report.add_error(
                    "publishing",
                    ReleaseError("Publishing the Public Information failed"),
                )
        else:
            self.report.add_error(
                "publishing", ReleaseError("Public Information won't be published")
            )
            self.printer.print_release_summary(self.report)
            raise ValueError("Creating the Public Information failed")

        self.printer.print_release_summary(self.report)
        if self.report.has_errors():
            raise ValueError("One of the steps in the VKGL release pipeline failed")

    def prepare_data(self, lab: str):
        """
        Prepare the data for the consensus per lab
        """
        warnings = []
        lab_name = self.config.labs[lab]["name"]
        data_preparer = DataPreparer(
            self.config, lab, self.processing_feedback, self.report, warnings
        )
        validator = Validator(
            lab, self.config, self.processing_feedback, self.report, warnings
        )
        try:
            self.print(f"📥 Retrieve {lab_name} raw data")
            if not self.config.slurm:
                DataRetriever(self.config, lab).get_raw_data()
            else:
                if Path(
                    f"{self.config.raw_data_folder}/{lab}/dataRetrieval.ok"
                ).exists():
                    self.print(
                        "✅ Data successfully retrieved via dataRetriever.sh", indent=1
                    )
                else:
                    raise ReleaseError(
                        f"No raw {lab_name} data available, please run the separate "
                        f"procedure first or set Slurm parameter to False"
                    )

            self.print(f"✏️ Prepare {lab_name} data")
            data_preparer.prepare_data()

            output = f"{self.config.processed_folder}/{lab}"
            self.print(f"⚖️ Compare new {lab_name} lab data with the previous release")
            compare = FileComparing(
                lab,
                lab_name,
                f"{self.config.cleaned_folder}/{lab}",
                self.report,
                warnings,
                output,
            )
            compare.compare_files()

            VariantRemover(self.config, lab, self.report, warnings).remove_variants()

            validator.validate_preprocessing()

            if warnings:
                self.report.add_warnings(lab_name, warnings)
        except ReleaseError as error:
            self.printer.print_error(error)
            self.report.add_error(lab_name, ReleaseError(error))

    async def normalise_lab_data(self, lab: str):
        """
        Normalise the variants for the consensus per lab
        """
        self.printer.print(f"🅥🅥 Normalise new {self.config.labs[lab]['name']} variants")
        try:
            warnings = []
            validator = Validator(
                lab, self.config, self.processing_feedback, self.report, warnings
            )
            input_file = f"{self.config.processed_folder}/{lab}/new_variants.tsv"
            with open(input_file, newline="") as infile:
                reader = csv.DictReader(infile, delimiter="\t")
                i = 0
                for batch in batched(list(reader), 1000):
                    i += 1
                    self.print(f"➡️ Run batch {i}", indent=1)
                    await Normalisation(self.config, lab, warnings).normalise(batch)

            validator.validate_normalisation()
            if warnings:
                self.report.add_warnings(self.config.labs[lab]["name"], warnings)
        except FileNotFoundError:
            self.printer.print_warning(
                ReleaseWarning("No new or updated variants found to normalise")
            )
        except ReleaseError as error:
            self.printer.print_error(error)
            self.report.add_error(self.config.labs[lab]["name"], ReleaseError(error))

    def create_consensus(self):
        try:
            warnings = Consensus(self.config).create_consensus()
            if warnings:
                self.report.add_warnings("consensus", warnings)
        except ReleaseError as error:
            self.printer.print_error(error)
            self.report.add_error("consensus", ReleaseError(error))

    def public_information(self):
        try:
            warnings = PublicInformation(self.config).generate_public_information()
            if warnings:
                self.report.add_warnings("PublicInfo", warnings)
        except ReleaseError as error:
            self.printer.print_error(error)
            self.report.add_error("PublicInfo", ReleaseError(error))


if __name__ == "__main__":
    try:
        asyncio.run(ReleasePipeline(Configuration()).run_release())
    except ValueError as e:
        print(f"\n‼️ {e} ‼️")
