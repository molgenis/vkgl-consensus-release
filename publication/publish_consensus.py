import tempfile
from pathlib import Path
from typing import List
from zipfile import ZipFile

from utils.configuration import Configuration
from utils.printer import Printer
from utils.report import ReleaseError


class Publisher:
    """
    This class is responsible for:
     1. Uploading new/updated consensus variants in the VKGL Consensus table
     2. Truncate and upload the updated Public Consensus
    """

    def __init__(self, config: Configuration, processing_feedback: List[dict]):
        self.config = config
        self.printer = Printer()
        self.print = self.printer.print
        self.processing_feedback = processing_feedback
        self.session = self.config.session
        self.session.signin(self.config.user, self.config.pwd)

    async def publish_consensus(self, public: bool = False):
        """
        Uploads VKGL consensus data into the database. This happens in two phases:
        1. New/existing rows are added/updated in the VKGL tables
        2. Remove variants that are deleted from the VKGL tables
        """
        with self.printer.indentation():
            if not public:
                await self._upload_consensus_data()
            else:
                self.session.truncate(table="PublicConsensus", schema="Public")
                await self._upload_public_consensus()
                self.session.truncate(table="Genomic variants", schema="Beacon")
                await self._upload_beacon_genomic_variants()

    async def _upload_consensus_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.print("📤 Upload new and updated Consensus data")
            archive_name = f"{tmpdir}/Consensus.zip"
            try:
                with ZipFile(archive_name, "w") as archive:
                    file_name = f"{self.config.consensus_folder}/Consensus.csv"
                    archive.write(file_name, "Consensus.csv")
                await self.session.upload_file(
                    schema="VKGL", file_path=Path(archive_name)
                )
            except Exception as e:
                raise ReleaseError("Error uploading Consensus data") from e

    async def _upload_public_consensus(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.print("📤 Upload Public Consensus")
            archive_name = f"{tmpdir}/PublicConsensus.zip"
            try:
                with ZipFile(archive_name, "w") as archive:
                    file_name = f"{self.config.consensus_folder}/PublicConsensus.csv"
                    archive.write(file_name, "PublicConsensus.csv")
                await self.session.upload_file(
                    schema="Public", file_path=Path(archive_name)
                )
            except Exception as e:
                raise ReleaseError("Error uploading Public Consensus") from e

    async def _upload_beacon_genomic_variants(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.print("📤 Upload Beacon Genomic Variants")
            archive_name = f"{tmpdir}/Beacon.zip"
            try:
                with ZipFile(archive_name, "w") as archive:
                    file_name = f"{self.config.consensus_folder}/Genomic variants.csv"
                    archive.write(file_name, "Genomic variants.csv")
                await self.session.upload_file(
                    schema="Beacon", file_path=Path(archive_name)
                )
            except Exception as e:
                raise ReleaseError("Error uploading Beacon Genomic Variants") from e
