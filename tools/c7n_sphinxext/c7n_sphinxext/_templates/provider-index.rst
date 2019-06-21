.. _{{provider_name|upper}}:

{{provider_name}} Reference
------------------------------------

Reference information about provider resources and their actions and filters.
See the :ref:`Generic Filters reference <filters>` for filters that can
be applies for all resources.

.. toctree::
   :maxdepth: 1
   :titlesonly:

{% for f in files %}
   {{f}}
{% endfor %}
