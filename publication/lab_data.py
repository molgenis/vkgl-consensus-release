import tempfile
from pathlib import Path
from typing import List
from zipfile import ZipFile

from utils.configuration import Configuration
from utils.printer import Printer
from utils.report import ReleaseError

from .delete_data import DataRemover
from .processing_feedback import FeedbackPublisher


class LabPublisher:
    """
    This class is responsible for copying data from the staging areas to the combined
    public tables.
    """

    def __init__(self, config: Configuration, processing_feedback: List[dict]):
        self.config = config
        self.printer = Printer()
        self.print = self.printer.print
        self.processing_feedback = processing_feedback
        self.session = self.config.session
        self.session.signin(self.config.user, self.config.pwd)

    async def publish_data(self, lab: str):
        """
        Uploads VKGL release data into the database. This happens in two phases:
        1. New/existing rows are added/updated in the Raw Lab Tables
        2. TO BE IMPLEMENTED!!! Remove all preprocessing feedback from previous release
        3. TO BE IMPLEMENTED!!! Remove variants that are deleted from the VKGL tables
        """
        self.printer.print(f"📝 Publish raw {self.config.labs[lab]['name']} data")
        with self.printer.indentation():
            DataRemover(self.config).processing_feedback(lab, "preprocessing")
            await self._upload_lab_data(lab)
            await FeedbackPublisher(
                self.config,
                self.processing_feedback,
                self.config.processed_folder,
            ).publish_feedback(lab, "preprocessing")

    async def _upload_lab_data(self, lab: str):
        with tempfile.TemporaryDirectory() as tmpdir:
            lab_name = self.config.labs[lab]["name"]
            self.print(f"📤 Upload raw {lab_name} data")
            archive_name = f"{tmpdir}/RawLabData.zip"
            try:
                with ZipFile(archive_name, "w") as archive:
                    folder = f"{self.config.processed_folder}/{lab}"
                    file_name = f"{folder}/{lab_name}.csv"
                    archive.write(file_name, f"{lab_name}.csv")

                await self.session.upload_file(
                    schema="RawLabData", file_path=Path(archive_name)
                )
            except Exception as e:
                raise ReleaseError(
                    f"Error uploading the " f"processed {lab_name} data"
                ) from e
