
"""
Centralized constants for the MyOCI toolkit.
"""

# Flags that expect a file path as their next argument
FILE_PATH_FLAGS = ["--ssh-authorized-keys-file", "--file", "--from-json", "--actions"]

# Regex patterns for PII redaction
OCID_PATTERN = r"ocid1\.[a-z0-9]+\.oc1\.[a-z0-9-]+\.[a-zA-Z0-9]+"
IP_PATTERN = r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"

# Filename for common schemas, to be ignored during template listing.
COMMON_SCHEMAS_FILENAME = "common_schemas.yaml"
