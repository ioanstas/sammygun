#!/usr/bin/env python3
"""
INSPIRE Validator: hardcoded run
- Only asks for Executable Test Suite ID.
- Everything else is hardcoded below.
"""
import os
import time
import json
import requests

# =========================
# HARD-CODED SETTINGS
# =========================
BASE = "https://inspire.ec.europa.eu"     # Validator base
API = f"{BASE}/validator/v2"

MODE = "local"                             # "local" | "remote" | "service"
LOCAL_XML_PATH = "./2b_HELEO-L1C-INSPIRE-THE-CORRECT - Version_3 - Copy.xml"   # used when MODE == "local"
REMOTE_XML_URL = "https://example.org/your.xml"  # used when MODE == "remote"
SERVICE_ENDPOINT = "https://example.org/wms?service=WMS&request=GetCapabilities"  # used when MODE == "service"

RUN_LABEL = "My XML validation"
POLL_EVERY = 5
POLL_TIMEOUT = 25 * 60  # 25 minutes

# =========================
# HELPERS
# =========================

def upload_local_xml(path: str) -> str:
    """Upload a local XML/GML file as a TestObject and return its ID."""
    url = f"{API}/TestObjects?action=upload"
    with open(path, "rb") as fh:
        files = {"fileupload": fh}  # required field name
        r = requests.post(url, files=files, timeout=1800)
    r.raise_for_status()
    payload = r.json()
    test_object_id = payload["testObject"]["id"]
    print(f"Uploaded test object id: {test_object_id}")
    return test_object_id

def start_test_run(label: str, executable_test_suite_ids, test_object: dict) -> str:
    """Create a test run and return its ID."""
    url = f"{API}/TestRuns"
    body = {
        "label": label,
        "executableTestSuiteIds": executable_test_suite_ids,
        "arguments": {"files_to_test": ".*", "tests_to_execute": ".*"},
        "testObject": test_object,
    }
    r = requests.post(
        url,
        data=json.dumps(body),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=60,
    )
    r.raise_for_status()
    resp = r.json()
    # Typical response path:
    run_id = (
        resp.get("EtfItemCollection", {})
            .get("testRuns", {})
            .get("TestRun", {})
            .get("id")
        or resp.get("id")
        or resp.get("testRunId")
    )
    if not run_id:
        raise RuntimeError(f"Could not find TestRun id in response: {resp}")
    print(f"Started TestRun: {run_id}")
    print(f"View in browser: {BASE}/validator/test-reports/details.html?id={run_id}")
    return run_id

def get_test_run_status(run_id: str) -> str:
    """Return textual status for a TestRun (e.g., RUNNING, COMPLETED, FAILED)."""
    url = f"{API}/TestRuns/{run_id}.json"
    r = requests.get(url, headers={"Accept": "application/json"}, timeout=60)
    r.raise_for_status()
    js = r.json()
    return (
        js.get("TestRun", {},).get("status")
        or js.get("status")
        or js.get("EtfItem", {},).get("status")
        or "UNKNOWN"
    )

def wait_until_finished(run_id: str) -> str:
    """Poll until run is COMPLETED/FAILED or timeout; return final status."""
    print("Waiting for the run to finish…")
    start = time.time()
    while True:
        status = get_test_run_status(run_id)
        print(f"  status: {status}")
        if status.upper() in {"COMPLETED", "FAILED"}:
            return status
        if (time.time() - start) > POLL_TIMEOUT:
            raise TimeoutError("Timeout waiting for the test run to finish.")
        time.sleep(POLL_EVERY)

def download_report_html(run_id: str, out_path: str) -> str:
    """Download HTML report for the run."""
    url = f"{API}/TestRuns/{run_id}.html"
    r = requests.get(url, timeout=180)
    r.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(r.content)
    print(f"Saved HTML report -> {out_path}")
    return out_path

# =========================
# MAIN
# =========================

if __name__ == "__main__":
    suite_id = input("Executable Test Suite ID (EID…): ").strip()
    if not suite_id:
        raise SystemExit("No Executable Test Suite ID provided.")

    # Build testObject depending on MODE
    if MODE == "local":
        if not os.path.isfile(LOCAL_XML_PATH):
            raise FileNotFoundError(f"LOCAL_XML_PATH not found: {LOCAL_XML_PATH}")
        test_object_id = upload_local_xml(LOCAL_XML_PATH)
        test_object = {"id": test_object_id}

    elif MODE == "remote":
        test_object = {"resources": {"data": REMOTE_XML_URL}}

    elif MODE == "service":
        test_object = {"resources": {"serviceEndpoint": SERVICE_ENDPOINT}}

    else:
        raise ValueError("MODE must be 'local', 'remote', or 'service'.")

    run_id = start_test_run(RUN_LABEL, [suite_id], test_object)
    final_status = wait_until_finished(run_id)
    print(f"Final status: {final_status}")

    out_file = f"report_{run_id}.html"
    download_report_html(run_id, out_file)
    print("Done.")
