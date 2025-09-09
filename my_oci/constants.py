
"""
Centralized constants for the MyOCI toolkit. Adheres to NoMagicValues.
"""

# Flags that expect a file path as their next argument
FILE_PATH_FLAGS = ["--ssh-authorized-keys-file", "--file", "--from-json", "--actions"]

# Regex patterns for PII redaction
OCID_PATTERN = r"ocid1\.[a-z0-9]+\.oc1\.[a-z0-9-]+\.[a-zA-Z0-9]+"
IP_PATTERN = r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"