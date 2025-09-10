
# Flags that expect a file path as their next argument
FILE_PATH_FLAGS = ["--ssh-authorized-keys-file", "--file", "--from-json", "--actions"]

# Regex patterns for PII redaction
# UPDATED: This pattern is now more permissive to catch malformed OCIDs.
# It matches the "ocid1." prefix and then any subsequent non-whitespace characters,
# ensuring that even invalid OCIDs provided as arguments are redacted.
OCID_PATTERN = r"ocid1\.[^\s'\"`]+"
IP_PATTERN = r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"

# Filename for common schemas, to be ignored during template listing.
COMMON_SCHEMAS_FILENAME = "common_schemas.yaml"