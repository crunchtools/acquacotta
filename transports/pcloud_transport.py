"""pCloud transport — thin adapter for JSON file operations on pCloud.

A first-run account has neither the Acquacotta folder nor pomodoros.json, so the
NOT_FOUND_CODES are ordinary "not there yet" answers that must read as an empty
file rather than propagate as errors.
"""

import requests

ACQUACOTTA_FOLDER_PATH = "/Acquacotta"

US_API_HOST = "api.pcloud.com"
EU_API_HOST = "eapi.pcloud.com"
API_HOSTS_BY_LOCATION_ID = {1: US_API_HOST, 2: EU_API_HOST}

REQUEST_TIMEOUT_SECONDS = 30

PCLOUD_OK = 0
PCLOUD_PARENT_DIR_NOT_FOUND = 2002
PCLOUD_DIR_NOT_FOUND = 2005
PCLOUD_FILE_NOT_FOUND = 2009
NOT_FOUND_CODES = (PCLOUD_PARENT_DIR_NOT_FOUND, PCLOUD_DIR_NOT_FOUND, PCLOUD_FILE_NOT_FOUND)


class PCloudError(Exception):
    """A pCloud API call returned a non-zero result code."""

    def __init__(self, code, message):
        super().__init__(f"pCloud API error {code}: {message}")
        self.code = code


class PCloudClient:
    """An authenticated pCloud REST session.

    Plays the same role for this transport that a googleapiclient `service`
    object plays for the Drive transport: it owns the credential and the
    endpoint, and knows nothing about Acquacotta's files.

    pCloud runs two independent regions and a token minted in one is invalid in
    the other, so `api_host` is bound to the token at link time and travels with
    it from then on.
    """

    def __init__(self, access_token, api_host=None):
        self._api_host = api_host or US_API_HOST
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {access_token}"

    @property
    def api_host(self):
        return self._api_host

    def call(self, method, params=None, files=None, tolerate=()):
        """Call a pCloud API method and return the decoded JSON body.

        Raises PCloudError unless the result code is 0 or listed in `tolerate`.
        """
        url = f"https://{self._api_host}/{method}"
        if files:
            response = self._session.post(url, params=params, files=files, timeout=REQUEST_TIMEOUT_SECONDS)
        else:
            response = self._session.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()

        body = response.json()
        result_code = body.get("result", PCLOUD_OK)
        if result_code != PCLOUD_OK and result_code not in tolerate:
            raise PCloudError(result_code, body.get("error", "Unknown error"))
        return body

    def fetch_content(self, url):
        """GET a pre-signed pCloud content URL and return the body as text.

        Deliberately not the authenticated session: getfilelink hands back a
        one-time URL on a content host, so the bearer token has no business
        being sent there.
        """
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.text


class PCloudTransport:
    def __init__(self, client, folder_path):
        self._client = client
        self._folder_path = (folder_path or ACQUACOTTA_FOLDER_PATH).rstrip("/")

    def _find_file(self, filename):
        """Find a file by name in the Acquacotta folder. Returns file ID or None."""
        stat = self._client.call("stat", {"path": f"{self._folder_path}/{filename}"}, tolerate=NOT_FOUND_CODES)
        if stat.get("result", PCLOUD_OK) != PCLOUD_OK:
            return None
        return stat.get("metadata", {}).get("fileid")

    def download_file(self, filename):
        """Download a file's content as a string. Returns None if not found."""
        file_id = self._find_file(filename)
        if file_id is None:
            return None
        link = self._client.call("getfilelink", {"fileid": file_id})
        hosts = link.get("hosts") or []
        if not hosts or not link.get("path"):
            return None
        return self._client.fetch_content(f"https://{hosts[0]}{link['path']}")

    def upload_file(self, filename, content):
        """Upload/overwrite a file in the Acquacotta folder.

        renameifexists=0 is load-bearing: without it pCloud sidesteps the write
        by saving pomodoros_1.json and leaving the real file stale.
        """
        self._client.call(
            "uploadfile",
            params={"path": self._folder_path, "renameifexists": 0, "nopartial": 1},
            files={"file": (filename, content.encode("utf-8"), "application/json")},
        )

    def ensure_directory(self):
        """Ensure the Acquacotta folder exists. Returns the folder path."""
        self._client.call("createfolderifnotexists", {"path": self._folder_path})
        return self._folder_path

    def file_exists(self, filename):
        """Check if a file exists in the folder."""
        return self._find_file(filename) is not None
