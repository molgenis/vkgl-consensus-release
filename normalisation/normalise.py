import csv
import re
from datetime import datetime
from pathlib import Path
from typing import List

import aiohttp

from publication.processing_feedback import FeedbackPublisher
from utils.configuration import Configuration
from utils.printer import Printer
from utils.report import ReleaseError, ReleaseWarning
from utils.utils import get_hash

from .variant_validator import VariantValidator


class Normalisation:
    """
    Ensure consistent variant representation using VariantValidator or equivalent
    """

    def __init__(
        self,
        config: Configuration,
        lab: str,
        warnings: List[ReleaseWarning],
    ):
        self.config = config
        self.lab = lab
        self.printer = Printer()
        self.session = self.config.session
        self.warnings = warnings
        self.processing_feedback: List[dict] = []

    async def normalise(self, data: List[dict]):
        normalised_folder = Path(f"{self.config.normalised_folder}/{self.lab}")
        normalised_folder.mkdir(parents=True, exist_ok=True)
        output_file = f"{normalised_folder}/{self.config.labs[self.lab]['name']}.csv"
        normalised_variants = []
        async with aiohttp.ClientSession() as session:
            processing_date = datetime.today().strftime("%Y-%m-%d")
            try:
                for row in data:
                    row: dict[str, str]  # type hint to prevent warnings
                    # Get genome reference build
                    row["genomeReferenceBuild"] = self.get_reference_build(row)
                    # Prepare URL
                    row["url"], row["url_type"] = VariantValidator(
                        self.warnings
                    ).build_vv_url(row)
                    if row["url_type"] == "missing_data":
                        feedback = {
                            self.lab: row["id"],
                            "lab": self.lab,
                            "processingStep": "normalisation",
                            "feedback": "Missing variant information",
                            "processingDate": processing_date,
                        }
                        self.processing_feedback.append(feedback)
                        continue
                    # Run variant validator
                    vv_response = await VariantValidator(
                        self.warnings
                    ).run_variant_validator(session, row["url"])
                    if not vv_response:
                        feedback = {
                            self.lab: row["id"],
                            "lab": self.lab,
                            "processingStep": "normalisation",
                            "feedback": "No normalisation results with mane_select "
                            "option, retry with select",
                            "processingDate": processing_date,
                            "normalisationURL": row["url"],
                        }
                        self.processing_feedback.append(feedback)
                        row["url"] = row["url"].replace("mane_select", "select")
                        self.printer.print(
                            f" => Retry with select " f"{row["id"]}", indent=2
                        )
                        vv_response = await VariantValidator(
                            self.warnings
                        ).run_variant_validator(session, row["url"])
                    if not vv_response:
                        feedback = {
                            self.lab: row["id"],
                            "lab": self.lab,
                            "processingStep": "normalisation",
                            "feedback": "No normalisation results",
                            "processingDate": processing_date,
                            "normalisationURL": row["url"],
                        }
                        self.processing_feedback.append(feedback)
                        continue
                    elif vv_response.get("validation_warnings", ""):
                        feedback = {
                            self.lab: row["id"],
                            "lab": self.lab,
                            "processingStep": "normalisation",
                            "feedback": vv_response["validation_warnings"],
                            "processingDate": processing_date,
                            "normalisationURL": row["url"],
                        }
                        self.processing_feedback.append(feedback)
                        if any(
                            "InvalidVariantError" in warning
                            for warning in vv_response["validation_warnings"]
                        ):
                            continue
                    # Process results from the variant validator
                    normalised_variant = self.process_vv_response(vv_response)
                    # If no grch37 results are available,
                    # variant not suitable for in the Consensus
                    if normalised_variant == "No normalised grch37 results available":
                        feedback = {
                            self.lab: row["id"],
                            "lab": self.lab,
                            "processingStep": "normalisation",
                            "feedback": "No normalised grch37 results available",
                            "processingDate": processing_date,
                            "normalisationURL": row["url"],
                        }
                        self.processing_feedback.append(feedback)
                        continue
                    if not normalised_variant.get("chromosome", ""):
                        feedback = {
                            self.lab: row["id"],
                            "lab": self.lab,
                            "processingStep": "normalisation",
                            "feedback": "No valid normalisation results",
                            "processingDate": processing_date,
                            "normalisationURL": row["url"],
                        }
                        self.processing_feedback.append(feedback)
                        continue
                    normalised_variant["rawLabData"] = row["id"]
                    for column in [
                        "variantType",
                        "location",
                        "exon",
                        "effect",
                        "classification",
                        "labUploadDate",
                    ]:
                        normalised_variant[column] = row.get(column, "")
                    chromosome = ""
                    if type(normalised_variant.get("chromosome", "")) is list:
                        feedback = {
                            self.lab: row["id"],
                            "lab": self.lab,
                            "processingStep": "normalisation",
                            "feedback": f"Multiple chromosomes returned: "
                            f"{normalised_variant.get('chromosome', '')}",
                            "processingDate": processing_date,
                            "normalisationURL": row["url"],
                        }
                        self.processing_feedback.append(feedback)
                        for item in normalised_variant.get("chromosome", ""):
                            if item == row["chromosome"].replace("chr", ""):
                                chromosome = item
                        if not chromosome:
                            feedback = {
                                self.lab: row["id"],
                                "lab": self.lab,
                                "processingStep": "normalisation",
                                "feedback": "Multiple chromosomes returned but "
                                "none could be mapped",
                                "processingDate": processing_date,
                                "normalisationURL": row["url"],
                            }
                            self.processing_feedback.append(feedback)
                            continue

                    if chromosome:
                        normalised_variant["chromosome"] = chromosome

                    _id = (
                        f"{normalised_variant['chromosome']}_"
                        f"{normalised_variant.get('start', '').strip()}_"
                        f"{normalised_variant.get('ref', '').strip()}_"
                        f"{normalised_variant.get('alt', '').strip()}_"
                        f"{normalised_variant.get('gene', '').strip()}"
                    )
                    normalised_variant["id"] = (
                        f"{self.lab.upper()}_{get_hash(_id)[0:10]}"
                    )
                    normalised_variant["genomeReferenceBuild"] = row[
                        "genomeReferenceBuild"
                    ].lower()
                    normalised_variant["vv_url"] = row["url"]
                    if not normalised_variant["gene"]:
                        normalised_variant["gene"] = "MISSING"
                    for column in ["alt", "altGRCh38", "ref", "refGRCh38"]:
                        if len(normalised_variant[column]) > 255 and normalised_variant[
                            "variantType"
                        ].lower() in [
                            "dup",
                            "del",
                            "deletion",
                        ]:
                            ref_alt_message = (
                                f"{column.capitalize()} too long to "
                                f"show for this {normalised_variant['variantType']}"
                            )
                            normalised_variant[column] = ref_alt_message
                    normalised_variants.append(normalised_variant)
            except Exception as e:
                raise ReleaseError(f"Something went wrong during normalisation: {e}")

            # Temporarily save processing feedback
            if self.processing_feedback:
                self.printer.print(
                    "✍️ Write normalisation feedback per variant to a temporary file",
                    indent=1,
                )
                FeedbackPublisher(
                    self.config,
                    self.processing_feedback,
                    self.config.normalised_folder,
                ).write_processing_feedback(lab=self.lab, temp=True)
            else:
                self.printer.print(
                    "📌 No normalisation feedback for this batch", indent=1
                )

            if normalised_variants:
                self.session.signin(self.config.user, self.config.pwd)
                schema_meta = self.session.get_schema_metadata(name="VKGL")
                fieldnames = []
                for table in schema_meta.tables:
                    if table.name == self.config.labs[self.lab]["name"]:
                        fieldnames = [column.name for column in table.columns]
                fieldnames.append("vv_url")
                with open(output_file, "a", newline="") as outfile:
                    writer = csv.DictWriter(
                        outfile, fieldnames=fieldnames, delimiter=","
                    )
                    if Path(output_file).stat().st_size == 0:
                        writer.writeheader()
                    writer.writerows(normalised_variants)
            else:
                raise ReleaseError(
                    "None of the new or updated variants are successfully normalised"
                )

    def process_vv_response(self, response):
        grch37 = response.get("primary_assembly_loci", {}).get("grch37", {})
        if not grch37:
            return "No normalised grch37 results available"
        grch38 = response.get("primary_assembly_loci", {}).get("grch38", {})
        protein = response.get("hgvs_predicted_protein_consequence", {}).get("tlr", "")

        hgvs_transcript_variant = response.get("hgvs_transcript_variant", "")
        if ":" in hgvs_transcript_variant:
            transcript_resp, c_dna = hgvs_transcript_variant.split(":", 1)
        else:
            # fallback: use whole string if no colon
            transcript_resp, c_dna = "", hgvs_transcript_variant

        return {
            "chromosome": (
                response.get("annotations", {}).get("chromosome")
                or grch37.get("vcf", {}).get("chr", "")
            ),
            "start": grch37.get("vcf", {}).get("pos", ""),
            "stop": self.get_genomic_stop(grch37.get("hgvs_genomic_description", "")),
            "ref": grch37.get("vcf", {}).get("ref", ""),
            "alt": grch37.get("vcf", {}).get("alt", ""),
            "gene": response.get("gene_symbol"),
            "cDNA": c_dna,  # changed: only the part after colon
            "transcript": transcript_resp,
            "protein": protein,
            "hgvs": grch37.get("hgvs_genomic_description", ""),
            "hgvsGRCh38": grch38.get("hgvs_genomic_description", ""),
            "posGRCh38": grch38.get("vcf", {}).get("pos", ""),
            "refGRCh38": grch38.get("vcf", {}).get("ref", ""),
            "altGRCh38": grch38.get("vcf", {}).get("alt", ""),
        }

    def get_reference_build(self, row: dict):
        if self.config.labs[self.lab]["genomeReferenceBuild"] == "inFile":
            return row[self.config.labs[self.lab]["genomeReferenceBuildColumn"]]
        else:
            return self.config.labs[self.lab]["genomeReferenceBuild"]

    @staticmethod
    def get_genomic_stop(hgvs):
        """
        Determine the genomic stop position from an HGVS genomic notation.
        Works for SNV, deletion, insertion, and delins.
        """
        m = re.search(r"g\.(\d+)(?:_(\d+))?", hgvs)
        if not m:
            return ""
        stop = int(m.group(2)) if m.group(2) else int(m.group(1))
        return stop

    def _warn(self, message: str):
        warning = ReleaseWarning(message)
        self.printer.print_warning(warning, indent=1)
        self.warnings.append(warning)
