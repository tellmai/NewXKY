"""Build-time license service address.

The release build must contain the public HTTPS address of the NewXKY license
service. Keep this value empty in source control; a packaged application with
an empty value cannot activate and shows a configuration error instead.
"""

LICENSE_SERVER_URL = 'https://license.newxky-license.com'  # Set to the public HTTPS address before building a release.
LICENSE_PUBLIC_KEY = 'uyQEoc6Zfm8GmQBK4tOWu0/Egx9NP8wfAV5ZByVyMtI='
