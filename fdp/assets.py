import datetime
import json
import os
import urllib.request

import ijson
import pandas as pd
import requests
import zstandard
from dagster import asset

from .resources import SpacescopeResource


@asset(compute_kind="python")
def raw_datacapstats_verified_clients() -> pd.DataFrame:
    """
    Verified Clients information from Datacapstats API.
    """
    url = "https://api.datacapstats.io/api/getVerifiedClients"

    data = pd.read_json(url, typ="series")["data"]
    df = pd.json_normalize(data)
    df["allowanceArray"] = df["allowanceArray"]

    return df


@asset(compute_kind="python")
def raw_storage_providers_filrep() -> pd.DataFrame:
    """
    Storage Providers information from Filrep API.
    """
    url = "https://api.filrep.io/api/v1/miners"

    storage_providers = pd.DataFrame(requests.get(url).json()["miners"])
    storage_providers = storage_providers.astype(str)

    return storage_providers.drop(columns=["id"])


@asset(compute_kind="python")
def raw_storage_providers_location_jimpick() -> pd.DataFrame:
    """
    Storage Providers location information from Jimpick's JSONs.
    """
    url = "https://geoip.feeds.provider.quest/synthetic-locations-latest.json"
    df = pd.read_json(url, typ="series")
    return pd.json_normalize(df["providerLocations"])


@asset(compute_kind="API")
def raw_storage_provider_daily_power(
    spacescope_api: SpacescopeResource
) -> pd.DataFrame:
    """
    Storage Providers daily power from Spacescope API.
    """
    FILECOIN_FIRST_DAY = datetime.date(2020, 10, 15)

    today = datetime.date.today()
    latest_day = today - datetime.timedelta(days=2)

    df_power_data = pd.DataFrame()

    for day in pd.date_range(FILECOIN_FIRST_DAY, latest_day, freq="d"):
        power_data = spacescope_api.get_storage_provider_power(
            date=day.strftime("%Y-%m-%d"), storage_provider=None
        )
        df_power_data = pd.concat(
            [df_power_data, pd.DataFrame(power_data)], ignore_index=True
        )

    return df_power_data


@asset(compute_kind="python")
def raw_filecoin_state_market_deals(context) -> None:
    """
    State Market Deals snapshot from Gliff S3 JSON.
    """
    urllib.request.urlretrieve(
        "https://marketdeals.s3.amazonaws.com/StateMarketDeals.json.zst",
        "/tmp/StateMarketDeals.json.zst",
    )

    context.log.info("Downloaded StateMarketDeals.json.zst")

    dctx = zstandard.ZstdDecompressor()
    input_path = "/tmp/StateMarketDeals.json.zst"
    output_path = "/tmp/ParsedStateMarketDeals.json"

    with open(input_path, "rb") as ifh, open(output_path, "wb") as ofh:
        reader = dctx.stream_reader(ifh)
        for k, v in ijson.kvitems(reader, ""):
            v["DealID"] = k
            ofh.write(json.dumps(v).encode("utf-8") + b"\n")

    context.log.info("Decompressed StateMarketDeals.json.zst")

    # Remove the temporary files
    os.remove("/tmp/StateMarketDeals.json.zst")