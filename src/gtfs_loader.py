import zipfile
import pandas as pd


def _find_file(z, filename):
    """
    Finds the correct path to a GTFS file inside a ZIP archive.
    For example:
        stops.txt
        latest/stops.txt
        google/stops.txt
    """
    for name in z.namelist():
        if name.endswith(filename):
            return name
    return None


def load_stops_from_gtfs_zip(path):
    """
    Load stops.txt from GTFS ZIP, even if it is inside a subfolder.
    """
    with zipfile.ZipFile(path, 'r') as z:

        stops_path = _find_file(z, "stops.txt")
        if stops_path is None:
            raise FileNotFoundError("stops.txt not found in GTFS ZIP")

        df = pd.read_csv(z.open(stops_path))
        return df


def load_stop_times_from_gtfs_zip(path):
    """
    Load stop_times.txt from GTFS ZIP, even if it is inside a subfolder.
    """
    with zipfile.ZipFile(path, 'r') as z:

        times_path = _find_file(z, "stop_times.txt")
        if times_path is None:
            raise FileNotFoundError("stop_times.txt not found in GTFS ZIP")

        df = pd.read_csv(z.open(times_path))
        return df
