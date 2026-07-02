import asyncio
import urllib.parse
from typing import List

from utils.printer import Printer
from utils.report import ReleaseWarning


class VariantValidator:
    API_BASE = "https://rest.variantvalidator.org/VariantValidator/variantvalidator"
    CONCURRENT_REQUESTS = 1
    SEMAPHORE = asyncio.Semaphore(CONCURRENT_REQUESTS)
    MAX_RETRIES = 5
    INITIAL_BACKOFF = 2  # seconds

    def __init__(self, warnings: List[ReleaseWarning]):
        self.printer = Printer()
        self.warnings = warnings

    @staticmethod
    def build_vv_url(variant: dict):
        api_url = f"{VariantValidator.API_BASE}/"
        if "hgvs" in variant:
            url = (
                f"{api_url}{variant['genomeReferenceBuild']}/"
                f"{urllib.parse.quote(variant['hgvs'])}/mane_select"
            )
            return url, "hgvs"

        if variant.get("variantType", "").lower() in ["del", "deletion"]:
            deletion = (
                f"{variant['chromosome']}:g.{variant['start']}_"
                f"{variant['stop']}del/"
            )
            url = f"{api_url}{variant['genomeReferenceBuild']}/{deletion}mane_select"
            return url, "deletion"

        if variant.get("variantType", "").lower() in ["dup"]:
            dup = f"{variant['chromosome']}:g.{variant['start']}_{variant['stop']}dup"
            url = f"{api_url}{variant['genomeReferenceBuild']}/{dup}/mane_select"
            return url, "duplication"

        if "." in (variant.get("ref") or "") or "." in (variant.get("alt") or ""):
            if variant["transcript"] and variant["cDNA"]:
                hgvs = f"{variant['transcript']}:{variant['cDNA']}"
                url = (
                    f"{api_url}{variant['genomeReferenceBuild']}/"
                    f"{urllib.parse.quote(hgvs)}/{variant['transcript']}"
                )
                return url, "c_nomen"
            else:
                return "", "missing_data"
        elif all(
            variant.get(key) not in [None, ""]
            for key in ["chromosome", "start", "ref", "alt"]
        ):
            pseudo = (
                f"{variant['chromosome'].replace('chr', '')}-{variant['start']}"
                f"-{variant['ref']}-{variant['alt']}"
            )
            if variant.get("transcript", ""):
                url = (
                    f"{api_url}{variant['genomeReferenceBuild']}/"
                    f"{pseudo}/{variant['transcript']}"
                )
            else:
                url = f"{api_url}{variant['genomeReferenceBuild']}/{pseudo}/mane_select"
            return url, "pseudo"

    async def run_variant_validator(self, session, url):
        retries = 0
        backoff = VariantValidator.INITIAL_BACKOFF
        async with VariantValidator.SEMAPHORE:
            while retries < VariantValidator.MAX_RETRIES:
                try:
                    async with session.get(
                        url, headers={"accept": "application/json"}, ssl=False
                    ) as resp:
                        if resp.status == 429:
                            await asyncio.sleep(backoff)
                            retries += 1
                            backoff *= 2
                            continue
                        resp.raise_for_status()
                        data = await resp.json()
                        key = next(
                            (
                                k
                                for k in data
                                if not k.startswith("flag")
                                and not k.startswith("metadata")
                            ),
                            None,
                        )
                        if not key:
                            self._warn(f"No relevant result key found for {url}")
                            return None
                        else:
                            return data[key]
                except Exception as e:
                    self._warn(f"Error for {url}: {e}")
                    return None
            self._warn(f"Failed for {url} after {VariantValidator.MAX_RETRIES} retries")
            return None

    def _warn(self, message: str):
        warning = ReleaseWarning(message)
        self.printer.print_warning(warning, indent=2)
        self.warnings.append(warning)
