# General methods
import hashlib
import re
from collections import OrderedDict
from datetime import datetime
from typing import List


def batched(list_: List, batch_size: int):
    """Yield successive n-sized batches from list_."""
    for i_ in range(0, len(list_), batch_size):
        yield list_[i_ : i_ + batch_size]


def extract_date(file):
    match = re.search(r"(\d{4}-?\d{2}-?\d{2})", file.name)
    if match:
        date_str = match.group(1).replace("-", "")
        return datetime.strptime(date_str, "%Y%m%d")
    match = re.search(r"(\d{4}-?\d{2})", file.name)
    if match:
        date_str = match.group(1).replace("-", "")
        return datetime.strptime(date_str, "%Y%m")
    return datetime.min


def get_row_count(file):
    n_rows = 0
    if file.suffix in [".csv", ".tsv", ".txt"]:
        with open(file, "r", encoding="utf-8") as f:
            n_rows = sum(1 for _ in f)
    if file.suffix == ".json":
        with open(file, "r", encoding="utf-8") as f:
            n_rows = sum(line.count("pathogenicity") for line in f) + 1
    return {"n_rows": n_rows}


def get_dict_value(data, key_list):
    key_exists = {key: data[key] for key in key_list if key in data}
    if key_exists:
        value = next(iter(key_exists.values()), None)
        return value.strip()
    return None


def add_key_suffix(data: dict, keys: list[str], suffix: str):
    for key in keys:
        data[f"{key}_{suffix}"] = data[key]
        del data[key]
    return data


def get_hash(input_value):
    return hashlib.sha256(bytes(input_value, "utf-8")).hexdigest()


def to_ordered_dict(rows: List[dict], id_attribute: str) -> OrderedDict:
    rows_by_id = OrderedDict()
    for row in rows:
        rows_by_id[row[id_attribute]] = row
    return rows_by_id
