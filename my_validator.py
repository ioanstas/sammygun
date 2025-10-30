import requests
import json
import time
import os

BASE = os.environ.get("INSPIRE_BASE", "https://inspire.ec.europa.eu")


# BASE = "https://inspire.ec.europa.eu"
API = f"{BASE}/validator/v2"

# You can choose one mode: "local", "remote", or "service"
MODE = "local"

# If MODE = local → path to your XML/GML file
LOCAL_XML_PATH = r"2b_HELEO-L1C-INSPIRE-THE-CORRECT - Version_3 - Copy.xml"

RUN_LABEL = "My XML validation"
POLL_EVERY = 5        # seconds between status checks
POLL_TIMEOUT = 25 * 60  # 25 minutes

url = f"{API}/ExecutableTestSuites"
headers = {"Accept": "application/json"}

response = requests.get(url, headers=headers)
print("Status code:", response.status_code)

executables_suites_results = response.json()
# Print nicely formatted (optional)
print(json.dumps(executables_suites_results, indent=3)[:])

def get_test_suite_ids_safe(executables_suites_results):
    """Safely extract all test suite IDs with error handling."""
    try:
        suites = executables_suites_results.get("EtfItemCollection", {}).get("executableTestSuites", {}).get("ExecutableTestSuite", [])
        if isinstance(suites, list):
            return [suite.get("id") for suite in suites if suite.get("id")]
        elif isinstance(suites, dict):
            return [suites.get("id")] if suites.get("id") else []
        return []
    except (KeyError, TypeError, AttributeError) as e:
        print(f"Error extracting test suite IDs: {e}")
        return []

get_test_suite_ids_safe(executables_suites_results)

def create_test_suite_lookup(executables_suites_results):
    """Create a lookup dictionary: label -> id."""
    suites = executables_suites_results["EtfItemCollection"]["executableTestSuites"]["ExecutableTestSuite"]
    return {suite["label"]: suite["id"] for suite in suites}

# Usage:
# lookup = create_test_suite_lookup(executables_suites_results)
# metadata_id = lookup.get("Common Requirements for ISO/TC 19139:2007 based INSPIRE metadata records.")
IDs_info = create_test_suite_lookup(executables_suites_results)


cc2b_id = IDs_info["Conformance Class 2b: INSPIRE data sets and data set series metadata for Monitoring"]
suite_id = IDs_info["Conformance Class 2b: INSPIRE data sets and data set series metadata for Monitoring"]
print(suite_id)

# ### POST ### upload files
upload_url = f"{API}/TestObjects?action=upload"

with open(LOCAL_XML_PATH, "rb") as f:
    files = {"fileupload": f}
    upload_response = requests.post(upload_url, files=files)
    
print("Upload status:", upload_response.status_code)
print("Response text:", upload_response.text)
upload_json = upload_response.json()
test_object_id = upload_json["testObject"]["id"]
print("Your test object ID:", test_object_id)