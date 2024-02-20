import os
import sys
from urllib.parse import urlparse
import re
import polars
import requests

API_URL = "https://data-sources.pdap.io/api/agencies/"


def get_page_data(page: int) -> dict:
    """Fetches a page of data from the API.

    Args:
        page (int): The page number to fetch.

    Returns:
        dict: The data for the page.
    """
    api_key = "Bearer " + os.getenv("VUE_APP_PDAP_API_KEY")
    response = requests.get(f"{API_URL}{page}", headers={"Authorization": api_key})
    if response.status_code != 200:
        raise Exception("Request to PDAP API failed. Response code:", response.status_code)
    return response.json()["data"]

def get_agencies_data() -> polars.DataFrame:
    """Retrives a list of agency dictionaries from file.

    Returns:
        list: List of agency dictionaries.
    """
    page = 1
    agencies_df = polars.DataFrame()
    results = get_page_data(page)

    while results:
        # Use list comprehension to clean results
        clean_results = [{k: "" if v is None else v for k, v in result.items()} for result in results]
        new_agencies_df = polars.DataFrame(clean_results)
        if not new_agencies_df.is_empty():
            agencies_df = polars.concat([agencies_df, new_agencies_df])
        page += 1
        results = get_page_data(page)

    return agencies_df


def parse_hostname(url: str) -> str:
    """Retrieves the hostname (example.com) from a url string.

    Args:
        url (str): Url to parse.

    Returns:
        str: The url's hostname.
    """
    try:
        # Remove leading and trailing whitespaces and quotes
        url = url.strip().strip('"')

        # Add "http://" to the url if it's not present
        if not re.match(r'http(s)?://', url):
            url = "http://" + url

        # Parse the url and retrieve the hostname
        parsed_url = urlparse(url)
        hostname = parsed_url.hostname

        # Remove "www." from the hostname
        hostname = re.sub(r'^www\.', '', hostname)
    except Exception as e:
        print(f"An error occurred while parsing the URL: {e}")
        raise e
    return hostname


def remove_http(url: str) -> str:
    """Removes http(s)://www. from a given url so that different protocols don't throw off the matcher.

    Args:
        url (str): Url to remove http from.

    Returns:
        str: The url without http(s)://www.
    """
    try:
        # Remove http(s)://www. and www. prefixes from the url
        url = re.sub(r'^(http(s)?://)?(www\.)?', '', url)
        # Ensure the url ends with a /
        if not url.endswith('/'):
            url += '/'
    except Exception as e:
        print(f"An error occurred while processing the URL: {e}")
        raise e
    return url


def remove_www(url: str) -> str:
    """Utility function for remove_http() and parse_hostname().

    Removes www. from a url to facilitate better matching for cases where www. is missing.

    Args:
        url (str): Url to remove www. from.

    Returns:
        str: The url without www.
    """
    if url.startswith("www."):
        url = url[4:]

    return url


def match_agencies(agencies, agency_hostnames, url):
    """Attempts to match a url with an agency.

    Args:
        agencies (list): List of agency dictionaries.
        agency_hostnames (list): List of corresponding agency hostnames.
        url (str): Url to match.

    Returns:
        dict: Dictionary of a match in the form {"url": url, "agency": matched_agency}.
    """
    url = url.strip().strip('"')
    url_hostname = parse_hostname(url)

    if url_hostname in agency_hostnames:
        # All agencies with the same hostname as the url are found
        matched_agency = [
            agencies[i] for i, agency_hostname in enumerate(agency_hostnames) if url_hostname == agency_hostname
        ]
    else:
        return {"url": url, "agency": [], "status": "No match found"}

    # More than one agency was found
    if len(matched_agency) > 1:
        url_no_http = remove_http(url)

        for agency in matched_agency:
            agency_homepage = remove_http(agency["homepage_url"])
            # It is assumed that if the url begins with the agency's url, then it belongs to that agency
            if url_no_http.startswith(agency_homepage):
                return {"url": url, "agency": agency, "status": "Match found"}
                break

        return {"url": url, "agency": [], "status": "Contested match"}

    return {"url": url, "agency": matched_agency[0], "status": "Match found"}


def identifier_main(urls_df: polars.DataFrame) -> polars.DataFrame
    agencies_df = get_agencies_data()
    # Filter out agencies without a homepage_url set
    # Define column names as variables for flexibility
    homepage_url_col = "homepage_url"
    hostname_col = "hostname"
    count_data_sources_col = "count_data_sources"
    max_data_sources_col = "max_data_sources"

    # Perform operations on DataFrame
    try:
        agencies_df = (
            agencies_df
            # Filter out rows without a homepage_url
            .filter(polars.col(homepage_url_col).is_not_null())
            .filter(polars.col(homepage_url_col) != "")
            # Add a new column 'hostname' by applying the parse_hostname function to 'homepage_url'
            .with_columns(polars.col(homepage_url_col).map_elements(parse_hostname).alias(hostname_col),
                          polars.col(count_data_sources_col).fill_null(0))
            # Add a new column 'max_data_sources' which is the max of 'count_data_sources' over 'hostname'
            .with_columns(polars.col(count_data_sources_col).max().over(hostname_col).alias(max_data_sources_col))
            # Filter rows where 'count_data_sources' equals 'max_data_sources'
            .filter(polars.col(count_data_sources_col) == polars.col(max_data_sources_col))
            # Keep only unique rows based on 'homepage_url'
            .unique(subset=[homepage_url_col])
        )
        print("Indentifying agencies...")
        # Add a new column 'hostname' by applying the parse_hostname function to 'url'
        urls_df = urls_df.with_columns(polars.col("url").map_elements(parse_hostname).alias("hostname"))

        # Join urls_df with agencies_df on 'hostname'
        matched_agencies_df = urls_df.join(agencies_df, on="hostname", how="left")

        # Replace all null values with an empty string
        matched_agencies_clean_df = matched_agencies_df.with_columns(polars.all().fill_null(""))
    except Exception as e:
        print(f"An error occurred while processing the data: {e}")
        raise e
    return matched_agencies_clean_df


if __name__ == "__main__":
    urls_df = polars.read_csv(sys.argv[1])
    matched_agencies_df = identifier_main(urls_df)

    matches_only = matched_agencies_df.filter(polars.col("hostname").is_not_null())

    num_matches = len(matches_only)
    num_urls = len(urls_df)
    percent = 100 * float(num_matches) / float(num_urls)
    print(f"\n{num_matches} / {num_urls} ({percent:0.1f}%) of urls identified")

    if not matches_only.is_empty():
        matches_only.select(polars.col("url"),
                            polars.col("name"),
                            polars.col("state_iso"),
                            polars.col("county_name"),
                            polars.col("municipality"),
                            polars.col("agency_type"),
                            polars.col("jurisdiction_type"),
                            polars.col("approved")).write_csv("results.csv")

    print("Results written to results.csv")
