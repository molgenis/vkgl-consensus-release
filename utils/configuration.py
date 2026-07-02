from collections import defaultdict
from pathlib import Path

import numpy as np
from decouple import Config, RepositoryEnv
from molgenis_emx2_pyclient import Client

from .utils import to_ordered_dict


class Configuration:
    """ """

    def __init__(self):
        credentials = Config(RepositoryEnv("credentials.txt"))
        self.url = credentials("URL")
        self.user = credentials("USERNAME")
        self.pwd = credentials("PASSWORD")
        self.slurm = credentials("SLURM", cast=bool)
        with Client(self.url) as session:
            session.signin(self.user, self.pwd)
            self.session = session
            session.set_schema("ReferenceLists")
            releases = sorted(session.get(table="Releases"), key=lambda x: x["id"])
            self.release = releases[-1]["id"]
            self.previous = releases[-2]["id"]
            self.cleaned_folder = Path("../cleaned")
            self.consensus_folder = Path("../consensus")
            self.normalised_folder = Path("../normalised")
            self.processed_folder = Path("../processed")
            self.raw_data_folder = Path("../rawData")

            labs = session.get(table="Labs", columns=["id", "name", "labSystem"])
            lab_systems = to_ordered_dict(
                session.get(table="LabSystems"), id_attribute="id"
            )
            for system in lab_systems:
                del lab_systems[system]["id"]
            for lab in labs:
                lab.update(lab_systems[lab["labSystem"]])

            self.labs = to_ordered_dict(labs, id_attribute="id")

            df_mapping = session.get("LabFile2VKGLColumns", as_df=True)
            # Reset notMapped columns to labFileColumn
            df_mapping["vkglColumn"] = np.where(
                df_mapping["vkglColumn"] == "notMapped",
                df_mapping["labFileColumn"],
                df_mapping["vkglColumn"],
            )
            labfile2vkgl_columns = df_mapping.to_dict(orient="records")
            self.labfile2vkgl_columns = defaultdict(dict)
            self.vkgl2labfile_columns = defaultdict(dict)
            for row in labfile2vkgl_columns:
                self.labfile2vkgl_columns[row["labSystem"]].update(
                    {row["labFileColumn"]: row["vkglColumn"]}
                )
                self.vkgl2labfile_columns[row["labSystem"]].update(
                    {row["vkglColumn"]: row["labFileColumn"]}
                )

            self.labfile_headers = dict()
            for lab in self.labs:
                self.labfile_headers[self.labs[lab]["labSystem"]] = "\t".join(
                    df_mapping[
                        df_mapping["labSystem"] == self.labs[lab]["labSystem"]
                    ].sort_values("columnOrder")["labFileColumn"]
                )

            classification_mapping = session.get("Lab2VKGLClassifications")
            self.lab2vkgl_classifications = defaultdict(dict)
            for row in classification_mapping:
                for lab_system in row["labSystems"].split(","):
                    self.lab2vkgl_classifications[lab_system][
                        row["labSystemClassification"]
                    ] = row["variantClassification"]
