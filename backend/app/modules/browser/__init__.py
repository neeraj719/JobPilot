"""Browser automation (CONTRACTS.md section 12).

Public surface, imported directly from the submodules so that importing this package
never pulls in Playwright:

* ``session``   - ``BrowserSessionHandle``, ``BrowserManager``, ``is_browser_available()``,
                  ``save_screenshot()``
* ``detector``  - ``detect_form(page)``, ``detect_form_from_html(html, url)``
* ``mapper``    - ``FieldMapper``, ``map_form(detected)``, ``slugify()``, ``is_sensitive_key()``
* ``autofill``  - ``fill_form(page, detected, answers)``, ``click_submit(page, detected)``
* ``schemas``   - ``DetectedForm``, ``DetectedField``, ``FieldOption``, ``Blocker``,
                  ``Mapping``, ``MappedField``, ``FillResult``

``runner.py`` (the ``ApplicationRunner`` orchestration) belongs to the applications module.
"""
