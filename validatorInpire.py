import os
import time
import json
import requests
from typing import List, Optional

BASE = os.environ.get("INSPIRE_BASE", "https://inspire.ec.europa.eu")
API = f"{BASE}/validator/v2"
TEST_URL = f"{API}/TestRuns.xml"
# How often to poll a running job (seconds)
POLL_EVERY = 5
POLL_TIMEOUT = 25 * 60  # 25 minutes max wait

def get_executable_test_suites() -> list:
    """Return the full list of executable test suites available on this validator."""
    url = f"{API}/ExecutableTestSuites"
    r = requests.get(url, headers={"Accept": "application/json"})
    r.raise_for_status()
    data = r.json()
    # The payload is an ETF item collection. We normalize into a flat list of dicts.
    suites = []
    # The structure can vary a bit; we try to be resilient:
    # Common paths: EtfItemCollection -> executableTestSuites -> ExecutableTestSuite (list or dict)
    col = data.get("EtfItemCollection", data)
    ets_block = None
    for key in ["executableTestSuites", "items", "ExecutableTestSuites"]:
        if key in col:
            ets_block = col[key]
            break
    if not ets_block:
        # Fallback: maybe the top-level already contains list-like items
        if isinstance(data, list):
            return data
        return suites

    entries = ets_block.get("ExecutableTestSuite") or ets_block
    if isinstance(entries, dict):
        entries = [entries]

    for e in entries:
        suites.append({
            "id": e.get("id") or e.get("@id") or e.get("localId"),
            "label": e.get("label") or e.get("title") or "",
            "description": e.get("description", ""),
        })
    return suites

def print_suites(suites: list, limit: Optional[int] = 30):
    """Pretty-print the first N suites."""
    print("\n== Available Executable Test Suites ==")
    for i, s in enumerate(suites[: (limit or len(suites))], start=1):
        print(f"[{i:02d}] {s['label']}  (id: {s['id']})")
    if limit and len(suites) > limit:
        print(f"... {len(suites) - limit} more (increase limit to see all)")

def upload_local_xml(path: str) -> str:
    """
    Upload a local XML/GML file as a TestObject.
    Returns the TestObject ID.
    """
    url = f"{API}/TestObjects?action=upload"
    with open(path, "rb") as fh:
        files = {"fileupload": fh}  # <-- field name required by the API
        r = requests.post(url, files=files)
    r.raise_for_status()
    payload = r.json()
    # Structure: {"testObject": {"id": "EID..."} , ...}
    test_object_id = payload["testObject"]["id"]
    print(f"Uploaded. TestObject id = {test_object_id}")
    return test_object_id

def make_test_object_from_url(resource_url: str) -> dict:
    """
    For remote XML: provide as 'data' resource.
    For service endpoints (WMS/WFS/etc.), use 'serviceEndpoint'.
    """
    return {"resources": {"data": resource_url}}


def start_test_run(label: str,
                   executable_test_suite_ids: List[str],
                   test_object: dict) -> str:
    """
    Start a test run. `test_object` can be {"id": "..."} from upload,
    or {"resources":{"data":"..."}} for a remote XML,
    or {"resources":{"serviceEndpoint":"..."}} for a service.
    """
    url = f"{API}/TestRuns"
    body = {
        "label": label,
        "executableTestSuiteIds": executable_test_suite_ids,
        # For XML/GML file validation, these are commonly used arguments:
        "arguments": {"files_to_test": ".*", "tests_to_execute": ".*"},
        "testObject": test_object,
    }
    r = requests.post(url, data=json.dumps(body),
                      headers={"Content-Type": "application/json",
                               "Accept": "application/json"})
    r.raise_for_status()
    resp = r.json()
    # Typical structure: EtfItemCollection -> testRuns -> TestRun -> id
    eid = (
        resp.get("EtfItemCollection", {})
            .get("testRuns", {})
            .get("TestRun", {})
            .get("id")
    )
    if not eid:
        # Fallbacks, just in case structure is slightly different:
        eid = resp.get("id") or resp.get("testRunId")
    if not eid:
        raise RuntimeError(f"Could not find test run id in response: {resp}")
    print(f"Started TestRun: {eid}")
    print(f"You can watch it in the browser: {BASE}/validator/test-reports/details.html?id={eid}")
    return eid

def get_test_run_status(test_run_id: str) -> dict:
    """Fetch JSON status for a TestRun."""
    url = f"{API}/TestRuns/{test_run_id}.json"
    r = requests.get(url, headers={"Accept": "application/json"})
    r.raise_for_status()
    return r.json()


def wait_until_finished(test_run_id: str):
    """Poll until COMPLETED/FAILED or timeout."""
    print("Waiting for the run to finish…")
    start = time.time()
    while True:
        js = get_test_run_status(test_run_id)
        # Common places where status appears:
        status = (
            js.get("TestRun", {}).get("status") or
            js.get("status") or
            js.get("EtfItem", {}).get("status")
        )
        print(f"  status: {status}")
        if status and status.upper() in {"COMPLETED", "FAILED"}:
            return status
        if (time.time() - start) > POLL_TIMEOUT:
            raise TimeoutError("Gave up waiting for the test run.")
        time.sleep(POLL_EVERY)


def download_report_html(test_run_id: str, out_path: str) -> str:
    """Save the HTML report to disk."""
    url = f"{API}/TestRuns/{test_run_id}.html"
    r = requests.get(url)
    r.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(r.content)
    print(f"Saved HTML report -> {out_path}")
    return out_path

suites = get_executable_test_suites()
print_suites(suites)
path = "2b_HELEO-L1C-INSPIRE-THE-CORRECT - Version_3 - Copy.xml"

if __name__ == "__main__":
    print(f"Using validator at: {BASE}")
    print("Step 1: fetch test suites...")
    suites = get_executable_test_suites()
    print_suites(suites, limit=25)

    # Let you pick a suite by number, OR paste a known ID
    choice = input("\nPick a suite number from the list (or press Enter to paste a suite ID): ").strip()
    if choice:
        idx = int(choice) - 1
        suite_id = suites[idx]["id"]
    else:
        suite_id = input("Paste an ExecutableTestSuite ID (EID…): ").strip()

    # Choose local file vs remote URL
    mode = input("\nTest object source: [1] Local file  [2] Remote XML URL  [3] Service endpoint URL  -> ").strip()
    if mode == "1":
        path = input("Path to your XML/GML file: ").strip().strip('"')
        test_object_id = upload_local_xml(path)
        test_object = {"id": test_object_id}
    elif mode == "2":
        url = input("Public URL to your XML: ").strip()
        test_object = make_test_object_from_url(url)
    else:
        svc = input("Service endpoint URL (e.g. WMS/WFS/Atom): ").strip()
        test_object = {"resources": {"serviceEndpoint": svc}}

    label = input("Give this run a short label (e.g., 'My XML check'): ").strip() or "My XML check"

    print("\nStep 2: start the run…")
    run_id = start_test_run(label, [suite_id], test_object)

    print("\nStep 3: poll until it finishes…")
    final = wait_until_finished(run_id)
    print(f"Finished with status: {final}")

    print("\nStep 4: download the HTML report…")
    out = f"report_{run_id}.html"
    download_report_html(run_id, out)
    print("\nAll done! Open the HTML report in your browser.")