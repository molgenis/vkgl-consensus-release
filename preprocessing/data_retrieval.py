import csv
import gzip
import json
import shutil
import subprocess
from pathlib import Path

from utils.configuration import Configuration
from utils.printer import Printer
from utils.report import ReleaseError


class DataRetriever:
    """
    Automatically retrieve and extract raw variant data from VKGL labs
    """

    def __init__(self, config: Configuration, lab: str):
        self.lab = lab
        self.config = config
        self.files = "rawLabFiles.txt"
        self.printer = Printer()
        # Create folder for download
        self.config.raw_data_folder.mkdir(parents=True, exist_ok=True)

    def get_raw_data(self):
        # Get the latest raw lab file from the nibbler transfer server
        self.get_files(self.config.previous)
        self.get_files(self.config.release)
        try:
            for file in sorted(
                Path(f"{self.config.raw_data_folder}/{self.lab}").iterdir(),
                key=lambda x: x.name,
            ):
                if not file.is_file():
                    continue
                if file.suffix == ".gz":
                    self.extract_files(file)
            for file in sorted(
                Path(f"{self.config.raw_data_folder}/{self.lab}").iterdir(),
                key=lambda x: x.name,
            ):
                if not file.is_file():
                    continue
                if file.suffix == ".json":
                    self.json2tsv(file)
                if file.suffix == ".csv":
                    self.csv2tsv(file)
        except Exception as e:
            raise ReleaseError(f"Something went wrong while retrieving data {e}")

    def get_files(self, release_version: str):
        account = f"umcg-vkgl-{self.lab}"
        if self.lab == "radboudmumc":
            account = "umcg-vkgl-radboud"

        self.printer.print(
            f"⬇️ Get {self.config.labs[self.lab]['name']} {release_version} lab data",
            indent=1,
        )
        rsync = [
            "rsync",
            "-av",
            f"--include-from={self.files}",
            "--exclude=*",
            f"--rsh=ssh -p 443 -l {account}",
            "--checksum",
            f"nb-transfer.hpc.rug.nl::home/{release_version}/",
            f"{self.config.raw_data_folder}/{self.lab}",
        ]
        run = subprocess.run(rsync, capture_output=True, text=True)

        if run.stderr:
            raise ReleaseError(run.stderr)

    def extract_files(self, file):
        self.printer.print(f"📤 Extract {file.name}", indent=1)
        with gzip.open(file, "rb") as file_in:
            with open(file.with_suffix(""), "wb") as file_out:
                shutil.copyfileobj(file_in, file_out)

    def json2tsv(self, file):
        self.printer.print(f"↔️ Convert {file.name} json to tsv", indent=1)
        with open(file, "r", encoding="utf-8") as json_file:
            data = json.load(json_file)
            flattened_data = []
            if "variants" in data:  # Emedgene format
                for row in data["variants"]:
                    flat_row = {}
                    for k, v in row.items():
                        if isinstance(v, str):
                            flat_row[k] = v
                        elif isinstance(v, list):
                            for i in v:
                                if isinstance(i, dict):
                                    if i["human_reference"] == "GRCh37":
                                        flat_row = dict(flat_row, **i)
                    flattened_data.append(flat_row)
            header = flattened_data[0].keys()
            with open(
                file.with_suffix(".tsv"), "w", encoding="utf-8", newline=""
            ) as tsv_file:
                writer = csv.DictWriter(
                    tsv_file,
                    fieldnames=header,
                    delimiter="\t",
                    extrasaction="ignore",
                )
                writer.writeheader()
                for row in flattened_data:
                    writer.writerow(row)

    def csv2tsv(self, file):
        self.printer.print(f"↔️ Convert {file.name} to tsv", indent=1)
        with open(file, "r", newline="", encoding="utf-8") as csvfile:
            csvreader = csv.reader(csvfile)
            with open(
                file.with_suffix(".tsv"), "w", newline="", encoding="utf-8"
            ) as tsv_file:
                tsv_writer = csv.writer(
                    tsv_file, delimiter="\t", quoting=csv.QUOTE_MINIMAL
                )
                tsv_writer.writerows(csvreader)
