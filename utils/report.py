import string
from collections import defaultdict
from dataclasses import dataclass, field
from typing import DefaultDict, List, Optional

import requests
from molgenis_emx2_pyclient.exceptions import NoSuchTableException


@dataclass(frozen=True)
class ReleaseWarning:
    """
    Class that contains a warning message. Use this when a problem occurs that
    shouldn't cancel the current action (for example ).
    """

    message: str


class ReleaseError(Exception):
    """
    Raise this exception when an error occurs that we can not recover from.
    """

    pass


@dataclass
class ReleaseReport:
    """
    Summary object. Stores errors and warnings that occur during processing.
    """

    labs: List[str]

    errors: DefaultDict[str, ReleaseError] = field(
        default_factory=lambda: defaultdict(list)
    )

    summary: DefaultDict[str, str] = field(default_factory=lambda: defaultdict(str))

    warnings: DefaultDict[str, List[ReleaseWarning]] = field(
        default_factory=lambda: defaultdict(list)
    )

    error: Optional[ReleaseError] = None

    def add_error(self, lab: str, error: ReleaseError):
        self.errors[lab] = error

    def add_warnings(self, lab: str, warnings: List[ReleaseWarning]):
        if warnings:
            self.warnings[lab].extend(warnings)

    def set_global_error(self, error: ReleaseError):
        self.error = error

    def has_lab_errors(self, lab) -> bool:
        return self.error is not None or (
            lab in self.errors and self.errors[lab] is not None
        )

    def has_errors(self) -> bool:
        return len(self.errors) > 0 or self.error

    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    def default_summary(self, lab_name: str):
        with open("SummaryTemplate.md", "r") as default:
            self.summary[lab_name] = default.read()
            self.update_summary(lab_name, {"Lab": lab_name})

    def update_summary(self, lab: str, data: dict):
        summary = string.Template(self.summary[lab])
        self.summary[lab] = summary.safe_substitute(**data)


class MolgenisRequestError(Exception):
    def __init__(self, error, response=False):
        self.message = error
        if response:
            self.response = response


def requests_error_handler(func):
    """
    Decorator that catches RequestExceptions and wraps them in a DirectoryError.
    """

    def inner_function(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (
            requests.exceptions.RequestException,
            MolgenisRequestError,
            NoSuchTableException,
        ) as e:
            raise ReleaseError("Request failed") from e

    return inner_function
