Codecrate
=========

**Codecrate** is a small utility that packs a Python codebase into a single
Markdown “context pack” and can unpack or patch it again.

It is designed for LLM workflows:

* **pack**: create a context pack Markdown from a repo
* **unpack**: reconstruct files from a packed Markdown
* **patch**: generate a diff-only Markdown patch between an old pack and a repo
* **apply**: apply a diff-only Markdown patch to a repo
* **validate-pack**: validate internal consistency of a pack (sha/markers/etc.)

.. toctree::
   :maxdepth: 2
   :caption: Documentation

   quickstart
   cli
   format
   api
   changelog

Indices
-------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
