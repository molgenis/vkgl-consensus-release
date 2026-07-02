import tempfile
from pathlib import Path
from typing import List
from zipfile import ZipFile

from publication.processing_feedback import FeedbackPublisher
from utils.configuration import Configuration
from utils.printer import Printer
from utils.report import ReleaseError

from .delete_data import DataRemover


class NormalisedPublisher:
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
        if self.session.signin_status != "signed in":
            self.session.signin(self.config.user, self.config.pwd)

    async def publish_data(self, lab: str):
        """
        Uploads VKGL release data into the database. This happens in two phases:
        1. New/existing rows are added/updated in the VKGL lab tables
        2. TO BE IMPLEMENTED!!! Remove all normalised feedback from the previous release
        3. TO BE IMPLEMENTED!!! Remove variants that are deleted from the VKGL tables
        """
        self.printer.print(
            f"📝 Publish normalised {self.config.labs[lab]['name']} data"
        )
        with self.printer.indentation():
            DataRemover(self.config).processing_feedback(lab, "normalisation")
            await self._upload_data(lab)
            await FeedbackPublisher(
                self.config,
                self.processing_feedback,
                self.config.normalised_folder,
            ).publish_feedback(lab, "normalisation")

    async def _upload_data(self, lab: str):
        lab_name = self.config.labs[lab]["name"]
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_name = f"{tmpdir}/VKGLData.zip"
            self.print("⬆️ Upload updated and new normalised lab data")
            try:
                with ZipFile(archive_name, "w") as archive:
                    folder = f"{self.config.normalised_folder}/{lab}"
                    file_name = f"{folder}/{lab_name}.csv"
                    archive.write(file_name, f"{lab_name}.csv")
                await self.session.upload_file(
                    schema="VKGL", file_path=Path(archive_name)
                )
            except Exception as e:
                raise ReleaseError(f"Error uploading Normalised {lab_name} data") from e
