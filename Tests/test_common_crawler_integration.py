import csv
import json
import os
import shutil
import tempfile
from unittest.mock import patch

from common_crawler.main import main
from common_crawler.cache import CommonCrawlerCacheManager


def validate_csv(directory, expected_values):
    """
    Validate that the CSV file contains the expected values
    Args:
        directory:
        expected_values:

    Returns:

    """
    # Create a dictionary mirroring the expected values, with the column names as keys, and all values initialized to false
    found_dict = {column: False for column in expected_values.keys()}

    # Find csv in directory and confirm there is only one
    csv_files = [file for file in os.listdir(directory) if file.endswith('.csv')]
    assert len(csv_files) == 1, "Multiple CSV files found in directory"
    csv_file = csv_files[0]

    with open(f"{directory}/{csv_file}", 'r') as file:
        reader = csv.reader(file)
        headers = next(reader)  # Get the header row

        for row in reader:
            row_dict = dict(zip(headers, row))  # Convert the row to a dictionary

            for column, expected_value in expected_values.items():
                if row_dict[column] == expected_value:
                    found_dict[column] = True

    return all(found_dict.values())


def test_cache_persistence():
    """
    Test that the cache can be saved to and loaded from a file
    """

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Create a cache and add data to it
        cache = CommonCrawlerCacheManager(
            file_name="test_cache.json",
            directory=tmp_dir,
        )
        cache.upsert("CC-MAIN-2020-24", "http://example.com", "example", 3)

        # Save the cache to a file
        cache.save_cache()

        # Recreate the cache and load the data from the file
        cache = CommonCrawlerCacheManager(
            file_name="test_cache.json",
            directory=tmp_dir,
        )

        # Assert that the loaded cache matches the original data
        assert cache.cache["CC-MAIN-2020-24"]["http://example.com"]["example"] == 3
        # assert cache.cache == mock_data, "Loaded cache does not match original data"

        # Reset cache and verify that it is is empty
        cache.reset_cache()
        assert cache.cache == {}

        # Clean up the test file

def validate_csvs(local_file_path, repo_file_path):
    # Check that the output file was created, and contains the expected data
    assert validate_csv('test_data', {
        'url': 'http://police.com'
    }), "Output csv file does not contain expected data"
    assert validate_csv('test_data', {
        'url': 'http://police.com/page2'
    }), "Output csv file does not contain expected data"
    # Additionally validate that the previous output file does not exist
    assert not validate_csv('test_data', {
        'url': 'http://keyword.com'
    }), "Output csv file does not contain expected data"

def validate_csv_reset_cache(local_file_path, repo_file_path):
    # Check that the output file was created, and contains the expected data
    assert validate_csv('test_data', {
        'url': 'http://keyword.com'
    }), "Output csv file does not contain expected data"



@patch('util.huggingface_api_manager.HuggingFaceAPIManager.upload_file')
def test_main_with_valid_args(mock_upload_file, mocker):
    """
    Test the main function with valid arguments
    """

    # Check if the directory exists
    if os.path.exists('test_data'):
        # Remove the directory and all its contents
        shutil.rmtree('test_data')

    # Replace the huggingface_api_manager upload_file function with one that
    # performs the validate_csvs function
    mock_upload_file.side_effect = validate_csv_reset_cache

    mock_parse_args = mocker.patch('common_crawler.main.parse_args')
    mock_args = mock_parse_args.return_value
    mock_args.common_crawl_id = 'CC-MAIN-9999-99'
    mock_args.url = '*.com'
    mock_args.keyword = 'keyword'
    mock_args.pages = 2
    mock_args.output_filename = 'test_output'
    mock_args.cache_filename = 'test_cache'
    mock_args.data_dir = 'test_data'
    mock_args.reset_cache = True

    # Mock the CommonCrawler to avoid actual web requests
    common_crawler_results = [
        # This result, containing the search keyword should be returned in the final output
        [{
            'url': 'http://keyword.com'
        }],
        # This result, because it does not contain the keyword, should not
        [{
            'url': 'http://not-in-results.com'
        }]
    ]
    mock_search_cc_index = mocker.patch('common_crawler.crawler.CommonCrawlerManager.search_common_crawl_index')
    mock_search_cc_index.side_effect = common_crawler_results

    # Common crawler sleeps for five seconds during execution -- this avoids that.
    mock_sleep = mocker.patch('time.sleep')
    mock_sleep.side_effect = lambda _: None

    # Call main with test arguments
    main()


    # Check that the cache file was created, and contains the expected data
    with open('test_data/test_cache.json', 'r') as file:
        cache = json.load(file)
        assert 'CC-MAIN-9999-99' in cache
        assert '*.com' in cache['CC-MAIN-9999-99']
        assert 'keyword' in cache['CC-MAIN-9999-99']['*.com']
        assert cache['CC-MAIN-9999-99']['*.com']['keyword'] == 2

    # Run main again with different arguments and no reset_cache enabled, to test persistence of cache and output files
    mock_upload_file.side_effect = validate_csvs
    mock_args.reset_cache = False
    mock_args.common_crawl_id = 'CC-MAIN-0000-00'
    mock_args.url = '*.gov'
    mock_args.keyword = 'police'
    mock_args.pages = 3
    # output_filename, cache_filename, and data_dir are unchanged
    common_crawler_results_2 = [
        # This result, containing the search keyword should be returned in the final output
        [{
            'url': 'http://police.com'
        }],
        # This result, because it does not contain the keyword, should not
        [{
            'url': 'http://military.com'
        }],
        # This result, because it does contain the keyword, should be returned in the final output
        [{
            'url': 'http://police.com/page2'
        }]
    ]
    mock_search_cc_index.side_effect = common_crawler_results_2


    # Call main with test arguments
    main()

    # Check that the cache file was created, and contains the expected data
    with open('test_data/test_cache.json', 'r') as file:
        cache = json.load(file)
        # Check the original data persists
        assert 'CC-MAIN-9999-99' in cache
        assert '*.com' in cache['CC-MAIN-9999-99']
        assert 'keyword' in cache['CC-MAIN-9999-99']['*.com']
        assert cache['CC-MAIN-9999-99']['*.com']['keyword'] == 2
        # Check the new data exists as well
        assert 'CC-MAIN-0000-00' in cache
        assert '*.gov' in cache['CC-MAIN-0000-00']
        assert 'police' in cache['CC-MAIN-0000-00']['*.gov']
        assert cache['CC-MAIN-0000-00']['*.gov']['police'] == 3

    # Clean up the test files
    if os.path.exists('test_data'):
        # Remove the directory and all its contents
        shutil.rmtree('test_data')
