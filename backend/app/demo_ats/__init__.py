"""Demo ATS - a fictional Greenhouse-style careers site served by this backend.

Mounted at ``/demo-ats`` (no auth) so the Playwright application flow can be demonstrated
end to end without touching any real employer website. ``catalog.py`` holds the postings
(including three clearly labelled "(Demo Careers)" mirrors on ``*.example`` domains);
``router.py`` serves the pages, ``jobs.json`` for ``DemoAtsAdapter`` and the apply form.
"""
