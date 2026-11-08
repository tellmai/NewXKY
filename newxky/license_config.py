"""Build-time license service address.

The release build must contain the public HTTPS address of the NewXKY license
service. Keep this value empty in source control; a packaged application with
an empty value cannot activate and shows a configuration error instead.
"""

LICENSE_SERVER_URL = ""  # Set to the public HTTPS address before building a release.
