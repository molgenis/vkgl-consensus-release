import csv
import tempfile
from pathlib import Path
from typing import List
from zipfile import ZipFile

from utils.configuration import Configuration
from utils.printer import Printer
from utils.report import ReleaseError

csv.field_size_limit(1000000)


class FeedbackPublisher:
    """
    This class is responsible for uploading the processing feedback into the database
    """

    def __init__(
        self,
        config: Configuration,
        processing_feedback: List[dict],
        folder: Path,
    ):
        self.config = config
        if self.config.session.signin_status != "signed in":
            self.config.session.signin(self.config.user, self.config.pwd)
        self.printer = Printer()
        self.print = self.printer.print
        self.processing_feedback = processing_feedback
        self.session = self.config.session
        self.folder = folder
        self.feedback = False

    async def publish_feedback(self, lab: str, step: str):
        """
        Uploads VKGL release feedback into the database. This happens in two phases:
        1. New/existing rows are added/updated in the Processing Feedback tables
        2. TO BE IMPLEMENTED => Remove redundant rows
        """
        self.printer.print(
            f"📝 Publish {self.config.labs[lab]['name']} {step} feedback"
        )
        with self.printer.indentation():
            if self.processing_feedback:
                self.feedback = True
                self.printer.print(f"✍️ Write {step} feedback per variant to file")
                self.write_processing_feedback(lab)

            self._add_saved_feedback(lab)

            if self.feedback:
                await self._upload_feedback(lab, step)
            else:
                self.printer.print(f"📌 No {step} feedback found")

    async def _upload_feedback(self, lab: str, step: str):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.print(f"⬆️ Upload {step} feedback")
            archive_name = f"{tmpdir}/ProcessingFeedback.zip"
            try:
                with ZipFile(archive_name, "w") as archive:
                    file_name = f"{self.folder}/{lab}/ProcessingFeedback.csv"
                    archive.write(file_name, "ProcessingFeedback.csv")
                await self.session.upload_file(
                    schema="RawLabData", file_path=Path(archive_name)
                )

            except Exception as e:
                raise ReleaseError(f"Error uploading {step} feedback") from e

    def _add_saved_feedback(self, lab: str):
        self.printer.print("🔍 Check if temporary saved feedback needs to be added")
        feedback_file = Path(f"{self.folder}/{lab}/ProcessingFeedback.csv")
        try:
            temp_file = f"{self.folder}/{lab}/feedback.tmp"
            if Path(temp_file).exists():
                with open(temp_file, newline="") as infile:
                    reader = csv.DictReader(infile)
                    header = reader.fieldnames
                    data_rows = list(reader)

                write_header = (
                    not feedback_file.exists() or feedback_file.stat().st_size == 0
                )

                with open(feedback_file, "a", newline="", encoding="utf-8") as outfile:
                    writer = csv.writer(outfile)
                    if write_header and header:
                        writer.writerow(header)
                    if data_rows:
                        writer.writerows([row.values() for row in data_rows])
                self.feedback = True
            else:
                self.printer.print("📌 No temporary feedback file found", indent=1)

        except Exception as e:
            raise ReleaseError(
                f"Something went wrong while added temporary feedback to "
                f"the feedback file {e}"
            )

    def write_processing_feedback(self, lab: str, temp: bool = False):
        mode = "w"
        filename = f"{self.folder}/{lab}/ProcessingFeedback.csv"
        if temp:
            filename = f"{self.folder}/{lab}/feedback.tmp"
            mode = "a"
        try:
            write_header = (
                not Path(filename).exists() or Path(filename).stat().st_size == 0
            )
            schema_meta = self.session.get_schema_metadata(name="RawLabData")
            fieldnames = []
            for table in schema_meta.tables:
                if table.name == "ProcessingFeedback":
                    fieldnames = [column.name for column in table.columns]
            with open(
                filename,
                mode,
                newline="",
            ) as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames, delimiter=",")
                if write_header:
                    writer.writeheader()
                writer.writerows(self.processing_feedback)
        except Exception as error:
            raise ReleaseError(
                f"Something went wrong while creating the "
                f"processing feedback file: {error}"
            )
