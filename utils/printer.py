from contextlib import contextmanager
from datetime import datetime

from .report import ReleaseError, ReleaseReport, ReleaseWarning


class Printer:
    """
    Simple printer that keeps track of indentation levels. Also has utility methods
    for printing some Report objects.
    """

    def __init__(self):
        self.indents = 0

    def indent(self):
        self.indents += 1

    def dedent(self):
        self.indents = max(0, self.indents - 1)

    def reset_indent(self):
        self.indents = 0

    def print(self, value: str = None, indent: int = 0):
        self.indents += indent
        if value:
            print(f"{'    ' * self.indents}{value}")
        else:
            print()
        self.indents -= indent

    def print_debug(self, value: str = None, indent: int = 0, debug: bool = False):
        if debug:
            self.print(value, indent)

    def print_header(self, text: str):
        title = f"{text}"
        border = "=" * (len(title) + 1)
        self.reset_indent()
        self.print()
        self.print(border)
        self.print(title)
        self.print(border)

    def print_error(self, error: ReleaseError):
        message = str(error)
        if error.__cause__:
            message += f" - Cause: {str(error.__cause__)}"
        self.print(f"❌ {message}")

    def print_warning(self, warning: ReleaseWarning, indent: int = 0):
        self.print(f"⚠️ {warning.message}", indent)

    def print_retrieval_summary(self, report: ReleaseReport):
        self.reset_indent()
        self.print()
        self.print("==========")
        self.print("📋 Summary")
        self.print("==========")

        for lab in report.labs:
            if lab in report.errors or report.error:
                message = f"❌ Retrieving {lab} data failed"
                if lab in report.warnings:
                    message += f" with {len(report.warnings[lab])} warning(s)"
            elif lab in report.warnings:
                message = (
                    f"⚠️ {lab} finished successfully with "
                    f"{len(report.warnings[lab])} warning(s)"
                )
            else:
                message = f"✅ Retrieving {lab} data finished successfully"

            self.print(message)

    def print_release_summary(self, report: ReleaseReport):
        self.print_pipeline_summary(report)
        self.save_data_summary(report)

    def print_pipeline_summary(self, report: ReleaseReport):
        self.reset_indent()
        self.print()
        self.print("==========")
        self.print(f"📋 Summary {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.print("==========")

        for lab in report.labs:
            if lab in ["consensus", "publishing", "PublicInfo"]:
                continue
            if lab in report.errors or report.error:
                message = f"❌ Processing {lab} data failed"
                if lab in report.warnings:
                    message += f" with {len(report.warnings[lab])} warning(s)"
            elif lab in report.warnings:
                message = (
                    f"⚠️ {lab} finished successfully with "
                    f"{len(report.warnings[lab])} warning(s)"
                )
            else:
                message = f"✅ Processing {lab} data finished successfully"

            self.print(message)

        if "consensus" in report.errors or report.error:
            message = f"❌ {report.errors['consensus']}"
            if "consensus" in report.warnings:
                message += f" with {len(report.warnings['consensus'])} warning(s)"
        elif "consensus" in report.warnings:
            message = (
                f"⚠️ Creating the consensus update finished successfully with "
                f"{len(report.warnings['consensus'])} warning(s)"
            )
        else:
            message = "✅ Creating the consensus update finished successfully"

        self.print(message)

        if "PublicInfo" in report.errors or report.error:
            message = f"❌ {report.errors['PublicInfo']}"
            if "PublicInfo" in report.warnings:
                message += f" with {len(report.warnings['PublicInfo'])} warning(s)"
        elif "PublicInfo" in report.warnings:
            message = (
                f"⚠️ Creating the PublicInfo finished successfully with "
                f"{len(report.warnings['PublicInfo'])} warning(s)"
            )
        else:
            message = "✅ Creating the PublicInfo finished successfully"

        self.print(message)

        if "publishing" in report.errors or report.error:
            message = f"❌ {report.errors['publishing']}"
            if "publishing" in report.warnings:
                message += f" with {len(report.warnings['publishing'])} warning(s)"
        elif "publishing" in report.warnings:
            message = (
                f"⚠️ Publishing the data finished successfully with "
                f"{len(report.warnings['publishing'])} warning(s)"
            )
        else:
            message = "✅ Publishing the data finished successfully"

        self.print(message)

    @staticmethod
    def save_data_summary(report: ReleaseReport):
        with open("DataSummary.md", "w") as file:
            file.write("**Summary**\n\n")
            for lab in report.labs:
                if len(report.summary[lab]) > 0:
                    file.write(report.summary[lab])
                    file.write("\n\n")
                else:
                    file.write(
                        f"**{lab}**\n=> No new data included in this " f"release\n\n"
                    )
            with open("Checklist.md", "r") as checklist:
                file.write(checklist.read())

    @contextmanager
    def indentation(self):
        self.indent()
        yield
        self.dedent()
